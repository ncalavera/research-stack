export const meta = {
  name: "resource-facts",
  description:
    "Re-sourcing (funnel step 5): for a valuable fact with no reliable backing, find a fresh authoritative OA source, fetch the full text, verify the fact is really stated there, assign a class.",
  whenToUse:
    "After pool and verification: facts that fell into MISATTRIBUTED/UNSOURCED or low-confidence but are valuable — send for re-sourcing. Run: Workflow({scriptPath:'./resource.js', args:{topic:'topic1', facts:[...]}}).",
  phases: [
    {
      title: "Sonnet",
      detail:
        "Bulk of facts: Sonnet finds an OA source → fetch → verify (chunks ≤8)",
    },
    {
      title: "Opus",
      detail:
        "Strategic: what Sonnet did not close, Opus digs deeper (≤3 at a time)",
    },
  ],
};

// Repo root + topic paths — Workflow calls this via scriptPath from any cwd, so
// paths must NOT be built from the current directory. ROOT is resolved from this
// file's own location, overridable via RESEARCH_STACK_ROOT. DATA_ROOT honours the
// vault (RESEARCH_VAULT) for topic data, falling back to the repo root.
import { fileURLToPath } from "url";
import { dirname } from "path";
const ROOT =
  process.env.RESEARCH_STACK_ROOT || dirname(fileURLToPath(import.meta.url)); // repo root for `cd ${ROOT} && ./resolve_oa.py | ./fetch_url.sh`
const DATA_ROOT = process.env.RESEARCH_VAULT || ROOT; // topic data root

const SCHEMA = {
  type: "object",
  required: [
    "found",
    "source",
    "source_class",
    "quote",
    "corrected_value",
    "confidence",
    "note",
  ],
  properties: {
    found: {
      type: "boolean",
      description:
        "true if a LIVE class-A/B source was found where the fact is really stated",
    },
    source: {
      type: ["string", "null"],
      description: "URL of the found backing source, or null",
    },
    source_class: {
      enum: ["A", "B", "C", null],
      description:
        "A primary/gov/science/guideline, B secondary/authoritative media, C blog/vendor/calculator",
    },
    quote: {
      type: ["string", "null"],
      description: "Verbatim quote from the page confirming the fact, or null",
    },
    corrected_value: {
      type: ["string", "null"],
      description:
        "If the fact's number needs to be corrected by the source — the correct value; otherwise null",
    },
    confidence: { enum: ["high", "medium", "low"] },
    note: {
      type: "string",
      description: "Brief: what was found, why this class/verdict",
    },
  },
};

const prompt = (fact, harder) =>
  `You are searching for an AUTHORITATIVE source for a specific fact (re-sourcing). The fact previously had no reliable backing — find it now.\n\n` +
  `## Fact\n${fact}\n\n` +
  `## How to search (in order; stop when you find a suitable source)\n` +
  `1. Scientific OA search (for scientific/medical facts): run via Bash \`cd ${ROOT} && ./resolve_oa.py --search "<English keywords for the fact>"\` — returns JSON with candidates (title, doi, source) and a fulltext field (full text of the best candidate). Compose the query in English around the substance of the fact.\n` +
  `2. For factual/guideline facts — use WebSearch targeting authoritative domains (government sites .gov/.gov.uk, science/universities .edu, topic-specific organisations), then fetch the page via Bash \`cd ${ROOT} && ./fetch_url.sh "<url>"\` (last line __SOURCE__ = alive).\n` +
  `3. You may call resolve_oa multiple times with different queries and iterate over candidates.\n\n` +
  (harder
    ? `## This is a SECOND ATTEMPT (initial search found no backing)\nDig deeper: rephrase the query 2-3 times differently, try both resolve_oa and WebSearch across different authoritative domains, go through several candidates. If after honest attempts there is no class-A/B backing — that is a valid result found=false, do not fabricate.\n\n`
    : ``) +
  `## Source class (strict)\n` +
  `A — primary/gov/science/official guideline (pubmed/pmc/peer-review, .gov, .edu, topic-specific NGOs and regulators). B — authoritative secondary (quality media, authoritative trade publications). C — blog/vendor/calculator/AI-content/SEO — NOT acceptable as backing, found=false.\n\n` +
  `## Verification\n` +
  `Open the source and confirm the fact is REALLY stated on the page (provide a verbatim quote). If the number differs — put the correct value in corrected_value. Do not stretch: no real class-A/B backing → found=false, source=null.\n` +
  `Return strictly according to the schema.`;

let A = args;
if (typeof A === "string") {
  try {
    A = JSON.parse(A);
  } catch {
    A = {};
  }
}
A = A || {};
const topic = A.topic || "topic1";
// Facts are accepted as strings OR objects {id?, text, hint?}. The agent prompt receives
// text + hint (otherwise interpolation yields "[object Object]"), but the RESULT
// stores only clean text — it becomes the fact text in the pool; hints don't belong there.
const factsRaw = A.facts || [];
const factsClean = factsRaw.map((f) => (typeof f === "string" ? f : f.text));
const facts = factsRaw.map((f) =>
  typeof f === "string"
    ? f
    : `${f.text}${f.hint ? `\n\nHint for where to look: ${f.hint}` : ""}${f.id ? `\n(id: ${f.id})` : ""}`,
);
const SONNET_CHUNK = A.sonnetChunk || 8; // ≤8 Sonnet at a time — lightweight, but memory-aware
const OPUS_CHUNK = A.opusChunk || 3; // ≤3 Opus at a time — heavy, don't crash the host
log(
  `re-sourcing: ${facts.length} facts, topic ${topic} (Sonnet chunk ${SONNET_CHUNK}, Opus chunk ${OPUS_CHUNK})`,
);

// Sliding window: always keep `limit` agents running — a slot frees, immediately take
// the next fact (no waiting for the whole group). Faster than barrier chunks, same memory bound.
async function mapLimit(items, limit, fn, phaseName) {
  const out = new Array(items.length);
  let next = 0;
  let done = 0;
  async function worker() {
    while (true) {
      const i = next++;
      if (i >= items.length) return;
      out[i] = await fn(items[i], i);
      done++;
      if (done % limit === 0 || done === items.length) {
        log(`${phaseName}: ${done}/${items.length}`);
      }
    }
  }
  const n = Math.min(limit, items.length);
  await Promise.all(Array.from({ length: n }, () => worker()));
  return out;
}

const ok = (v) =>
  v &&
  v.found &&
  v.source &&
  (v.source_class === "A" || v.source_class === "B");

// Stage 1 — Sonnet over all facts (bulk, cheap and easy).
phase("Sonnet");
const s1 = await mapLimit(
  facts,
  SONNET_CHUNK,
  async (fact, i) => {
    const v = await agent(prompt(fact, false), {
      label: `sonnet:${i + 1}`,
      phase: "Sonnet",
      schema: SCHEMA,
      model: "sonnet",
    });
    return {
      fact: factsClean[i],
      idx: i,
      ...(v || { found: false, source: null, note: "agent null" }),
    };
  },
  "Sonnet",
);

// Stage 2 — Opus strategically: only what Sonnet did not close (found=false / class C / low).
const failedIdx = s1.map((x, k) => (ok(x) ? -1 : k)).filter((k) => k >= 0);
log(
  `Sonnet closed ${s1.length - failedIdx.length}/${s1.length}; sending ${failedIdx.length} to Opus`,
);

phase("Opus");
const fixes = await mapLimit(
  failedIdx,
  OPUS_CHUNK,
  async (k, _i) => {
    const v = await agent(prompt(facts[k], true), {
      label: `opus:${k + 1}`,
      phase: "Opus",
      schema: SCHEMA,
      model: "opus",
    });
    return {
      k,
      res: {
        fact: factsClean[k],
        idx: k,
        ...(v || { found: false, source: null, note: "opus null" }),
      },
    };
  },
  "Opus",
);

// Merge: where Opus found acceptable backing — replace the Sonnet result.
const out = s1.slice();
for (const f of fixes) {
  if (f && ok(f.res)) out[f.k] = f.res;
}

const recovered = out.filter(ok);
log(`A/B backing found: ${recovered.length} of ${facts.length}`);

const resourceResult = {
  topic,
  total: facts.length,
  recovered_count: recovered.length,
  opus_retried: failedIdx.length,
  results: out,
};

// Save to disk from within the workflow (atomize.js/check_claims.js pattern) —
// build_pool reads topics/<topic>/pool_resourced.json; the orchestrator does not move it by hand.
const resourcedPath = `${DATA_ROOT}/topics/${topic}/pool_resourced.json`;
await agent(
  `Write exactly the following JSON to file ${resourcedPath} (create the folder if needed, use Bash mkdir -p). Do not change anything in the content:\n\n${JSON.stringify(resourceResult, null, 1)}`,
  { label: `save:pool_resourced`, model: "haiku" },
);
log(`saved → ${resourcedPath}`);

return resourceResult;
