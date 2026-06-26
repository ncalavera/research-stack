export const meta = {
  name: "check-claims",
  description:
    "Core claim verifier: engine report → atoms → honest source fetch → bias-aware verdict per claim. Unverified claims never reach the report silently.",
  whenToUse:
    "When you need to run ONE engine report through per-atom fact-checking: confirmed / misattributed / dead source / no source, with a final link. Run: Workflow({scriptPath:'./check_claims.js', args:{topic:'topic2', engine:'perplexity_sonar'}}). Depends on topics/<topic>/engines/<engine>.json (report+sources). Writes verdicts to topics/<topic>/verdicts/<engine>.json itself (args.round=N → suffix __rN) — the orchestrator does not need to move the result.",
  phases: [
    {
      title: "Atomize",
      detail:
        "Split the report into atomic claims with attribution to the cited source",
    },
    {
      title: "Prefetch",
      detail:
        "Parallel source pre-fetch: one Haiku agent per URL chunk runs prefetch.py, pages are cached to disk, the judge reads files directly via Read/Grep",
    },
    {
      title: "Judge",
      detail:
        "Sonnet judges by URL groups (one agent = all claims for one source); Opus handles escalated claims one-by-one",
    },
    {
      title: "Counter",
      detail:
        "Counter-check for 'not stated' (has_number=true only): Sonnet searches for a verbatim quote in the file via Read/Grep, overturns false 'no' results when the source is class A/B",
    },
  ],
};

// check-claims: Atomize (Opus) → Prefetch (Haiku, prefetch.py) → Judge by URL groups (Sonnet) → optional Opus per claim.
// Sonnet has the right not to guess: when uncertain about a number/substitution it sets escalate=true, sending the claim to Opus.
// Hard Opus triggers on top of self-escalation: number + unreliable engine, or "confirmed" under low-trust profile.
// Bias profiles (docs/2026-06-05-engine-bias-profiles.md) are injected into the judge prompt per engine.
// The judge reads the page file directly via Read/Grep — no inline excerpt, no 40k truncation.

// Repository root + topic paths: the script lives in the repo root, but Workflow
// calls it via scriptPath from any cwd, so paths must NOT be built from the
// current directory. ROOT is resolved from this file's own location (so it works
// from any cwd), overridable via RESEARCH_STACK_ROOT. DATA_ROOT honours the vault
// (RESEARCH_VAULT) for topic data, falling back to the repo root.
import { fileURLToPath } from "url";
import { dirname } from "path";
const ROOT =
  process.env.RESEARCH_STACK_ROOT || dirname(fileURLToPath(import.meta.url)); // repo root for `cd ${ROOT} && python3 …` engine-script calls
const DATA_ROOT = process.env.RESEARCH_VAULT || ROOT; // topic data root

// ─── Bias profiles: what the filter checks FIRST for each engine ───
const PROFILES = {
  claude_deepresearch: {
    trust: "high",
    rule: "Primary bias is omission, not fabrication. Trust the facts, but if a claim sounds like 'open question / no data' — check whether the real answer is in the source. Claude has no inline links: map claim→source using the sources list.",
  },
  openai_deep: {
    trust: "high for science/gov",
    rule: "Solid core on science/health/gov — on live A-sources. BUT salaries, niche figures, and named vacancies often hang on 404/login-walls/dead job pages, and it cites 404 as backing. Double-check all numbers from vacancies/salaries; do NOT accept a 404/login URL as backing.",
  },
  exa_research: {
    trust: "medium",
    rule: "Provides volume but embeds inline URLs in the text that are NOT in its own sources — these cannot be verified, treat as BROKEN_SOURCE. Job links rot into unrelated pages: open and verify the page actually shows that vacancy.",
  },
  perplexity_deep: {
    trust: "low on numbers",
    rule: "Primary number fabricator. Massively attributes salary ranges and named vacancies to aggregator walls (Indeed/salary.com/Glassdoor returning 403). Maximum distrust mode: verify EVERY salary/quantitative claim on the page; a cite to a salary aggregator with no visible number in the excerpt → MISATTRIBUTED.",
  },
  perplexity_sonar: {
    trust: "medium",
    rule: "Misattribution: supplies a plausible live source in which the claimed fact is NOT present (technation '5+ years', YouTube webinars without a transcript). Occasional false 'no data' when the cited page actually has the data. Verify the number is really in the excerpt; YouTube/webinar is not a source; double-check negations.",
  },
  exa_answer: {
    trust: "low on quality",
    rule: "Supplies class-C sources — AI-vendor blogs, calculators, personal blogs — and generic pages that don't contain the claimed fact. Strictly cut by source class (C = not backing for a specific fact) and verify the number is really confirmed.",
  },
  gemini: {
    trust: "do not trust",
    rule: "All links are vertexaisearch redirects, unauditable (fetch_url.sh returns __UNAUDITABLE__). Do NOT accept a Gemini fact as confirmed: BROKEN_SOURCE if the only backing is vertexaisearch.",
  },
};
const DEFAULT_PROFILE = {
  trust: "default",
  rule: "No profile — apply default checks: verify the claimed fact is really present in the excerpt of a live class-A/B source.",
};
const HIGH_TRUST = new Set(["claude_deepresearch", "openai_deep"]);

// ─── Structured output schemas ───
const ATOMIZE_SCHEMA = {
  type: "object",
  required: ["claims"],
  properties: {
    claims: {
      type: "array",
      items: {
        type: "object",
        required: ["id", "text", "source", "has_number"],
        properties: {
          id: { type: "string", description: "c1, c2, …" },
          text: {
            type: "string",
            description: "Atomic verifiable claim (one idea)",
          },
          source: {
            type: ["string", "null"],
            description:
              "URL of the source this claim is anchored to in the report; null if no link",
          },
          has_number: {
            type: "boolean",
            description:
              "true if the claim contains a number/range/salary/percentage — a narrow spot requiring strict verification",
          },
        },
      },
    },
  },
};

// FETCH_SCHEMA removed: the Haiku agent no longer returns an excerpt.
// prefetch.py returns an index {url→{file,alive,via,bytes}} — we use PREFETCH_SCHEMA.
const PREFETCH_SCHEMA = {
  type: "object",
  required: ["entries"],
  properties: {
    entries: {
      type: "array",
      items: {
        type: "object",
        required: ["url", "file", "alive", "via"],
        properties: {
          url: { type: "string" },
          file: {
            type: ["string", "null"],
            description: "Absolute path to the page file, or null",
          },
          alive: { type: "boolean" },
          via: {
            type: "string",
            description:
              "direct / jina / firecrawl / firecrawl_stealth / dead / unauditable / timeout",
          },
        },
      },
    },
    index_path: { type: "string" },
    urls_total: { type: "number" },
    urls_alive: { type: "number" },
    urls_dead: { type: "number" },
  },
};

const VERDICT_SCHEMA = {
  type: "object",
  required: [
    "label",
    "final_source",
    "source_class",
    "corrected_value",
    "confidence",
    "escalate",
    "fabricated",
    "note",
    "quote",
  ],
  properties: {
    label: {
      enum: [
        "SUPPORTED",
        "PARTIAL",
        "MISATTRIBUTED",
        "BROKEN_SOURCE",
        "UNSOURCED",
      ],
      description:
        "SUPPORTED — a live A/B source confirms the claim in full (if there is a number — it matches); PARTIAL — the substance is confirmed by a live A/B source but the number/detail in the claim differs from what the page says (the source gives a different value); the claim is NOT discarded — it goes into the report with the number FROM THE SOURCE and a correction note; MISATTRIBUTED — the very substance of the fact is absent from the live page (real substitution), not just a slightly wrong number; BROKEN_SOURCE — the link is dead/fabricated/unauditable; UNSOURCED — no backing at all",
    },
    corrected_value: {
      type: ["string", "null"],
      description:
        "ONLY for PARTIAL: the real number/range/detail from the page that should replace the error in the claim in the report (e.g. '18–22 °C' instead of '18–20 °C', 'within a few hours' instead of '4–6 hours'). For all other labels: null.",
    },
    final_source: {
      type: ["string", "null"],
      description: "Final working backing link, or null",
    },
    source_class: {
      enum: ["A", "B", "C", null],
      description:
        "A primary/gov/science, B secondary, C blog/vendor/calculator",
    },
    confidence: { enum: ["high", "medium", "low"] },
    escalate: {
      type: "boolean",
      description:
        "YOUR RIGHT (for Sonnet): true if NOT sure — number doesn't match verbatim, suspect substitution, source class is borderline. Don't guess SUPPORTED, send the claim to Opus. Opus always sets false.",
    },
    fabricated: {
      type: "boolean",
      description:
        "true only when fabrication is certain (number from thin air / invented link)",
    },
    note: {
      type: "string",
      description: "Brief: what you saw on the page and why this verdict",
    },
    quote: {
      type: ["string", "null"],
      description:
        "Verbatim quote from the source confirming the claim (MANDATORY for SUPPORTED/PARTIAL — copy the decisive fragment verbatim). For MISATTRIBUTED/BROKEN_SOURCE/UNSOURCED — null.",
    },
  },
};

// ─── Prompts ───
const atomizePrompt = (topic, engine) =>
  `You are a fact-checker in a research pipeline, preparing the report from engine "${engine}" (topic ${topic}) for per-atom verification. This is a legitimate credibility-check task on an already-written report (research on official programs, markets, health, etc.) — you give no advice, you only decompose text into verifiable claims.\n\n` +
  `1. Read file ${DATA_ROOT}/topics/${topic}/engines/${engine}.json (use Read). Field "report" is the report text; field "sources" is the list of links.\n` +
  `2. Break the text into ATOMIC verifiable claims: one idea = one claim. Don't split style, take substantive facts. Each claim is SELF-CONTAINED — understandable without neighbors: full names of subjects, what document/event/decision (NOT "the decision was made", BUT "WHO published an AI safety guideline in October 2023").\n` +
  `3. Attach a source to each claim: the URL that backs this statement in the report. Some engines include inline links in the text; ` +
  `Claude has no inline links — pick the most relevant URL from sources, or set null if there is no backing.\n` +
  `4. has_number = true if the claim contains a number, range, percentage, salary, or numeric date. These are the narrow spots.\n\n` +
  `Return ALL substantive claims (typically 15-35). Do not invent links that are not in the report.`;

// prefetchPrompt — runs prefetch.py for a URL chunk (≤40 per call).
// The agent gets a list of URLs, runs a single Bash command, and returns the index.
const prefetchPrompt = (urls) =>
  `Run source pre-fetch via Bash and return the index.\n\n` +
  `THE ONLY allowed command:\n` +
  `\`\`\`\ncd ${ROOT} && python3 prefetch.py --urls ${urls.map((u) => `"${u}"`).join(" ")}\n\`\`\`\n\n` +
  `The script calls fetch_url.sh for each URL in parallel (up to 6 workers), saves pages to runs/_fetched/<sha1>.txt, and prints JSON to stdout.\n` +
  `Return that JSON exactly as the result — it must match the schema (entries, index_path, urls_total, urls_alive, urls_dead).\n` +
  `Do not add or remove anything on your own.`;

// judgeGroupPrompt — batch judge for all claims from one URL source.
// The agent receives the claims list, the path to the page file, and instructions to read via Read/Grep.
// The file is not truncated — the page can be large; Grep helps locate the relevant fragment.
const BATCH_VERDICT_SCHEMA = {
  type: "object",
  required: ["verdicts"],
  properties: {
    verdicts: {
      type: "array",
      items: {
        type: "object",
        required: [
          "id",
          "label",
          "final_source",
          "source_class",
          "corrected_value",
          "confidence",
          "escalate",
          "fabricated",
          "note",
          "quote",
        ],
        properties: {
          id: { type: "string" },
          label: {
            enum: [
              "SUPPORTED",
              "PARTIAL",
              "MISATTRIBUTED",
              "BROKEN_SOURCE",
              "UNSOURCED",
            ],
          },
          corrected_value: { type: ["string", "null"] },
          final_source: { type: ["string", "null"] },
          source_class: { enum: ["A", "B", "C", null] },
          confidence: { enum: ["high", "medium", "low"] },
          escalate: { type: "boolean" },
          fabricated: { type: "boolean" },
          note: { type: "string" },
          quote: { type: ["string", "null"] },
        },
      },
    },
  },
};

const judgeGroupPrompt = (
  claimsInGroup,
  url,
  topic,
  engine,
  profile,
  fetchEntry,
) => {
  const fileInstruction =
    fetchEntry.alive && fetchEntry.file
      ? `Page file: ${fetchEntry.file}\n` +
        `Use Read to read the file. If the file is long — use Grep to search for relevant fragments by keywords from each claim. The file is NOT truncated — search the full text, not just the beginning.`
      : `Page is DEAD (alive=false, via=${fetchEntry.via}). For all claims from this URL — verdict BROKEN_SOURCE.`;

  const claimsBlock = claimsInGroup
    .map((c) => `- id=${c.id} has_number=${c.has_number}\n  Claim: ${c.text}`)
    .join("\n\n");

  return (
    `You are a fact-checker judge (Sonnet). Topic ${topic}, engine "${engine}" (trust: ${profile.trust}).\n\n` +
    `## Source for this group\n${url}\nFetch: alive=${fetchEntry.alive}, via=${fetchEntry.via}.\n${fileInstruction}\n\n` +
    `## Claims to verify (all reference this URL)\n${claimsBlock}\n\n` +
    `## Bias-aware check (engine profile)\n${profile.rule}\n\n` +
    `## Verdict rules\n` +
    `For each claim with has_number=true: first check the SUBSTANCE (is the fact on the page), then the number.\n` +
    `  • Substance present AND number matches → SUPPORTED.\n` +
    `  • Substance present, number differs → PARTIAL, corrected_value = real value from the page.\n` +
    `  • Substance absent → MISATTRIBUTED.\n` +
    `For claims without a number: SUPPORTED if substance is present, MISATTRIBUTED if not.\n` +
    `- BROKEN_SOURCE — alive=false (dead/unauditable).\n` +
    `- UNSOURCED — no backing at all.\n\n` +
    `ESCALATION RIGHT (escalate=true): if you cannot verify the number or are in doubt — send the claim to Opus. Certain — escalate=false.\n` +
    `final_source — working backing link or null. corrected_value only for PARTIAL. fabricated=true when fabrication is certain.\n` +
    `In the note field — ALWAYS cite the specific text fragment you relied on.\n` +
    `Field quote: for SUPPORTED/PARTIAL — ALWAYS copy the decisive fragment verbatim from the source text that confirms the claim. For MISATTRIBUTED/BROKEN_SOURCE/UNSOURCED — null.\n` +
    `Return verdicts with one object per claim (all ids from the list must be present).`
  );
};

// judgePrompt — single judge for an escalated claim (Opus).
// Takes one claim + the fetched entry from the prefetch index.
const judgePrompt = (claim, topic, engine, profile, fetchEntry, forOpus) => {
  const fileInstruction =
    fetchEntry.alive && fetchEntry.file
      ? `Page file: ${fetchEntry.file}\n` +
        `Use Read to read it. If the file is long — use Grep to search by keywords from the claim. The file is NOT truncated, search the full text.`
      : `Page is DEAD (alive=false, via=${fetchEntry.via}).`;

  return (
    `You are a ${forOpus ? "SENIOR judge (Opus): final decision on a disputed claim" : "fact-checker judge (Sonnet)"}. ` +
    `Topic ${topic}, engine "${engine}" (trust: ${profile.trust}).\n\n` +
    `## Claim\n${claim.text}\n\n` +
    `## Stated source\n${claim.source || "(no link)"}\nFetch: alive=${fetchEntry.alive}, via=${fetchEntry.via}.\n${fileInstruction}\n\n` +
    `## Bias-aware check (engine profile)\n${profile.rule}\n\n` +
    `## Narrow spot\n` +
    (claim.has_number
      ? `The claim HAS a number. First check the SUBSTANCE (is the fact on the page), then the number.\n` +
        `  • Substance present AND number matches verbatim/within the page's range → SUPPORTED.\n` +
        `  • Substance present but number differs → PARTIAL, corrected_value = real value from the page.\n` +
        `  • The very substance of the fact is not on the page → MISATTRIBUTED.\n`
      : `No number — check meaning: the stated fact is really present on the page (SUPPORTED) or not (MISATTRIBUTED).\n`) +
    `\n## Verdict\n` +
    `- SUPPORTED — source alive (alive=true), class A/B, confirms the claim in full.\n` +
    `- PARTIAL — substance confirmed by a live A/B source, number/detail differs; fill corrected_value.\n` +
    `- MISATTRIBUTED — source alive but the very substance of the fact is not there.\n` +
    `- BROKEN_SOURCE — alive=false (dead/unauditable).\n` +
    `- UNSOURCED — no backing at all.\n` +
    (forOpus
      ? `You are the final authority: decide conclusively, escalate is ALWAYS false.`
      : `ESCALATION RIGHT: if you cannot verify the number or are in doubt — set escalate=true. Certain — escalate=false.`) +
    ` final_source — working backing link or null. corrected_value only for PARTIAL. fabricated=true when fabrication is certain. In note — cite the specific fragment.` +
    ` Field quote: for SUPPORTED/PARTIAL — ALWAYS copy the decisive fragment verbatim from the source. For MISATTRIBUTED/BROKEN_SOURCE/UNSOURCED — null.`
  );
};

// Counter-check for "not stated" (MISATTRIBUTED): tries to OVERTURN the judge's negative,
// re-reading the full text and searching for a verbatim quote. Catches false "no" on composite claims and paraphrase.
const COUNTER_SCHEMA = {
  type: "object",
  required: ["found", "quote", "source_class", "confidence", "note"],
  properties: {
    found: {
      type: "boolean",
      description:
        "true if the text REALLY contains backing for the claim substance (found a verbatim quote); otherwise false",
    },
    quote: {
      type: ["string", "null"],
      description:
        "Verbatim quote from the text confirming the claim substance, or null if not found",
    },
    source_class: { enum: ["A", "B", "C", null] },
    confidence: { enum: ["high", "medium", "low"] },
    note: {
      type: "string",
      description: "Brief: what was found/not found and why",
    },
  },
};

// counterPrompt — counter-check for MISATTRIBUTED (has_number=true only).
// Model: sonnet (data shows 1 overturn in 152 runs on Opus — cheaper).
// Agent reads file via Read/Grep — no inline excerpt, no truncation.
const counterPrompt = (claim, engine, profile, fetchEntry, firstNote) =>
  `The first judge ruled that this fact IS NOT STATED IN THE SOURCE (verdict "not stated"). Your task is to try to OVERTURN that ruling.\n\n` +
  `## Claim\n${claim.text}\n\n` +
  `## First judge's conclusion (this is what we challenge)\n${firstNote || "(none)"}\n\n` +
  `## Source (${engine}, trust ${profile.trust})\n` +
  (fetchEntry.alive && fetchEntry.file
    ? `Page file: ${fetchEntry.file}\n` +
      `Use Read to read the FULL file. If the file is long — use Grep to search by keywords from the claim. The file is NOT truncated — search the full text.\n`
    : `Page is DEAD — found=false, quote=null.\n`) +
  `\n## How to challenge\n` +
  `1. The claim may be COMPOSITE — check whether its SUBSTANCE (core) is confirmed, even if not every word is verbatim. One unproven add-on must not sink a confirmed core.\n` +
  `2. Look for meaning, not exact wording: paraphrase in the source counts.\n` +
  `3. The claim HAS a number — it must appear verbatim, otherwise found=false.\n` +
  `4. Found real backing for the substance — found=true and provide a VERBATIM quote (quote). Stretching is forbidden: the quote must confirm exactly this.\n` +
  `5. Really not there — found=false, quote=null (the first judge was right).`;

// whether Opus is needed on top of the Sonnet verdict
const needsOpus = (claim, v, engine) =>
  v.escalate === true ||
  ((v.label === "SUPPORTED" || v.label === "PARTIAL") && claim.has_number) ||
  (v.label === "SUPPORTED" && !HIGH_TRUST.has(engine));

// ─── Orchestration ───
const spent0 = budget.spent(); // telemetry: tokens at the start of this run

// args sometimes arrives as a JSON string — normalise
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
const engine = A.engine || "perplexity_sonar";
const profile = PROFILES[engine] || DEFAULT_PROFILE;
log(`input: topic=${topic}, engine=${engine} (args type=${typeof args})`);

phase("Atomize");
// Fallback: atoms can be supplied pre-built via args.claims (when the atomize agent
// deterministically fails on a specific file — e.g. claude_deepresearch/topic2,
// false content-filter refusal). The orchestrator (skill) slices the atoms itself and passes them here.
let atom;
if (Array.isArray(A.claims) && A.claims.length) {
  // Hydration: the orchestrator may pass either full atom objects or just
  // their id strings ("c1") / objects without source. In those cases we pull
  // fields (text, source, has_number) from topics/<topic>/atoms/<engine>.json by id —
  // otherwise a claim without source silently becomes UNSOURCED (silent failure when passing ids).
  const needsHydration = A.claims.some(
    (c) =>
      typeof c === "string" ||
      (c && typeof c === "object" && !c.source && c.id),
  );
  if (needsHydration) {
    // The workflow sandbox has no direct file access — hydrate via
    // a lightweight Haiku agent: it reads atoms/<engine>.json and returns
    // the requested atoms by id in full (with source/text/has_number).
    const wantIds = A.claims.map((c) => (typeof c === "string" ? c : c.id));
    const hyd = await agent(
      `Read file ${DATA_ROOT}/topics/${topic}/atoms/${engine}.json (field claims — array of objects {id,text,source,has_number}). ` +
        `Return ONLY the objects whose id is in this list: ${JSON.stringify(wantIds)}. ` +
        `Each — in full, verbatim, changing nothing. If an id is not in the file — skip it.`,
      {
        label: `hydrate:${engine}`,
        phase: "Atomize",
        model: "haiku",
        schema: ATOMIZE_SCHEMA,
      },
    );
    const byId = {};
    for (const a of (hyd && hyd.claims) || []) byId[a.id] = a;
    const hydrated = A.claims.map((c) => {
      // full object with source takes priority; otherwise use the atoms file
      if (typeof c === "object" && c.source) return c;
      const id = typeof c === "string" ? c : c.id;
      return { ...(byId[id] || {}), ...(typeof c === "object" ? c : {}) };
    });
    const stillUnsourced = hydrated.filter((c) => !c.source).length;
    log(
      `atoms passed externally: ${A.claims.length} (hydrated from atoms/${engine}.json; still without source: ${stillUnsourced})`,
    );
    atom = { claims: hydrated };
  } else {
    log(`atoms passed externally: ${A.claims.length} (atomize agent skipped)`);
    atom = { claims: A.claims };
  }
} else {
  atom = await agent(atomizePrompt(topic, engine), {
    label: `atomize:${engine}`,
    phase: "Atomize",
    schema: ATOMIZE_SCHEMA,
    model: "opus", // foundation: atom slicing and source attribution determines all subsequent analysis
  });
}
const claims = (atom && atom.claims) || [];
log(
  `${engine}/${topic}: ${claims.length} atoms (${claims.filter((c) => c.has_number).length} with numbers)`,
);

// ─── Prefetch phase: parallel pre-fetch of all unique URLs ───
// Claims without source → UNSOURCED, do not enter prefetch at all.
// URLs are chunked at 40 each; each chunk is one Haiku agent with prefetch.py.
// Result — fetchIndex: {url → {file, alive, via}}.

phase("Prefetch");

// Deduplicate URLs from claims (preserve first-occurrence order via Map).
const urlSet = new Map(); // url → true
for (const c of claims) {
  if (c.source) urlSet.set(c.source, true);
}
const uniqueUrls = [...urlSet.keys()];
log(`unique URLs for pre-fetch: ${uniqueUrls.length}`);

// Split into chunks of 40 URLs — to avoid overloading a single agent.
const PREFETCH_CHUNK = 40;
const urlChunks = [];
for (let i = 0; i < uniqueUrls.length; i += PREFETCH_CHUNK) {
  urlChunks.push(uniqueUrls.slice(i, i + PREFETCH_CHUNK));
}

// Run chunks in parallel via parallel() — each chunk is one Haiku agent.
const fetchIndex = {}; // url → {file, alive, via}
if (urlChunks.length > 0) {
  const chunkResults = await parallel(
    urlChunks.map((chunk, ci) => async () => {
      const result = await agent(prefetchPrompt(chunk), {
        label: `prefetch:chunk${ci}`,
        phase: "Prefetch",
        schema: PREFETCH_SCHEMA,
        model: "haiku",
      });
      return result;
    }),
  );
  // Merge all chunks into a single index.
  for (const r of chunkResults) {
    if (r && Array.isArray(r.entries)) {
      for (const e of r.entries) {
        fetchIndex[e.url] = { file: e.file, alive: e.alive, via: e.via };
      }
    }
  }
}

const urlsTotal = uniqueUrls.length;
const urlsDead = uniqueUrls.filter((u) => !fetchIndex[u]?.alive).length;
log(
  `prefetch done: ${urlsTotal} URLs, alive: ${urlsTotal - urlsDead}, dead: ${urlsDead}`,
);

// ─── Judge phase: batch by URL groups (Sonnet) + single escalation (Opus) ───
// Claims without source → UNSOURCED deterministically, without an agent.
// Claims with a dead URL → BROKEN_SOURCE deterministically, without an agent.
// Live URLs: group claims by URL, one Sonnet agent per group.
// Escalated claims within a group → single Opus per claim.

phase("Judge");

// Split into three buckets: unsourced, broken, alive-groups.
const unsourcedClaims = claims.filter((c) => !c.source);
const sourcedClaims = claims.filter((c) => c.source);

// Group by URL.
const urlGroups = new Map(); // url → [claim, ...]
for (const c of sourcedClaims) {
  if (!urlGroups.has(c.source)) urlGroups.set(c.source, []);
  urlGroups.get(c.source).push(c);
}

// Deterministic verdicts without an agent.
const deterministicResults = [];

// UNSOURCED: claims without source.
for (const c of unsourcedClaims) {
  deterministicResults.push({
    id: c.id,
    text: c.text,
    source: c.source,
    has_number: c.has_number,
    source_alive: false,
    fetch_via: "none",
    source_class: null,
    label: "UNSOURCED",
    final_source: null,
    corrected_value: null,
    confidence: "high",
    fabricated: false,
    tier: "deterministic",
    escalated: false,
    disagreement: null,
    counter: null,
    quote: null,
    note: "no link — no backing",
  });
}

// Run judges in parallel by URL groups.
const groupJudgePromises = [];
for (const [url, groupClaims] of urlGroups.entries()) {
  const fetchEntry = fetchIndex[url] || {
    file: null,
    alive: false,
    via: "missing",
  };

  // BROKEN_SOURCE: dead URL — all claims in the group without an agent.
  if (!fetchEntry.alive) {
    for (const c of groupClaims) {
      deterministicResults.push({
        id: c.id,
        text: c.text,
        source: c.source,
        has_number: c.has_number,
        source_alive: false,
        fetch_via: fetchEntry.via,
        source_class: null,
        label: "BROKEN_SOURCE",
        final_source: null,
        corrected_value: null,
        confidence: "high",
        fabricated: false,
        tier: "deterministic",
        escalated: false,
        disagreement: null,
        counter: null,
        quote: null,
        note: `URL dead (${fetchEntry.via}) — no agent`,
      });
    }
    continue;
  }

  // Live URL: one Sonnet agent per group.
  groupJudgePromises.push(async () => {
    const batchResult = await agent(
      judgeGroupPrompt(groupClaims, url, topic, engine, profile, fetchEntry),
      {
        label: `judge-group:${url.slice(-40)}`,
        phase: "Judge",
        schema: BATCH_VERDICT_SCHEMA,
        model: "sonnet",
      },
    );

    // Index verdicts by id.
    const verdictMap = {};
    if (batchResult && Array.isArray(batchResult.verdicts)) {
      for (const v of batchResult.verdicts) {
        verdictMap[v.id] = v;
      }
    }

    // For each claim in the group: escalate or finalise.
    const groupResults = [];
    for (const claim of groupClaims) {
      const v = verdictMap[claim.id];
      if (!v) {
        // Agent did not return a verdict for this id — mark as error.
        groupResults.push({
          id: claim.id,
          text: claim.text,
          source: claim.source,
          has_number: claim.has_number,
          source_alive: fetchEntry.alive,
          fetch_via: fetchEntry.via,
          source_class: null,
          label: "BROKEN_SOURCE",
          final_source: null,
          corrected_value: null,
          confidence: "low",
          fabricated: false,
          tier: "err",
          escalated: false,
          disagreement: null,
          counter: null,
          quote: null,
          note: "agent did not return a verdict for this claim",
        });
        continue;
      }

      let final = v,
        tier = "sonnet",
        disagreement = null;

      // Opus: single escalation per claim.
      if (needsOpus(claim, v, engine)) {
        const o = await agent(
          judgePrompt(claim, topic, engine, profile, fetchEntry, true),
          {
            label: `opus:${claim.id}`,
            phase: "Judge",
            schema: VERDICT_SCHEMA,
            model: "opus",
          },
        );
        if (o) {
          tier = "opus";
          if (o.label !== v.label) {
            disagreement = {
              sonnet: v.label,
              opus: o.label,
              sonnet_note: v.note,
            };
          }
          final = o;
        }
      }

      // COUNTER-CHECK "not stated": has_number=true only, model sonnet.
      // Data shows 1 overturn in 152 runs on Opus — switching to Sonnet.
      let counter = null;
      if (
        final.label === "MISATTRIBUTED" &&
        fetchEntry.alive &&
        claim.has_number
      ) {
        const cc = await agent(
          counterPrompt(claim, engine, profile, fetchEntry, final.note),
          {
            label: `counter:${claim.id}`,
            phase: "Counter",
            schema: COUNTER_SCHEMA,
            model: "sonnet",
          },
        );
        if (cc && cc.found && cc.quote) {
          const cls = cc.source_class || final.source_class;
          if (cls === "A" || cls === "B") {
            // Text really contains the fact AND the source is of acceptable class → overturn.
            counter = {
              overturned: true,
              quote: cc.quote,
              from: "MISATTRIBUTED",
            };
            final = {
              ...final,
              label: "SUPPORTED",
              source_class: cls,
              confidence: cc.confidence || "medium",
              note: `[counter-check overturned "not stated"→"stated"] quote: "${cc.quote}" — ${cc.note}`,
            };
            tier = "counter";
          } else {
            // Fact is in the text but source is class C — not counted as backing.
            counter = {
              overturned: false,
              quote: cc.quote,
              class_blocked: cls,
              note: `text contains the fact but source class ${cls} — not accepted as backing`,
            };
            final = {
              ...final,
              source_class: cls,
              note: `${final.note} [counter-check: fact in text but source class ${cls} — not backing, quote: "${cc.quote}"]`,
            };
          }
        } else if (cc) {
          counter = { overturned: false, note: cc.note };
        }
      }

      groupResults.push({
        id: claim.id,
        text: claim.text,
        source: claim.source,
        has_number: claim.has_number,
        source_alive: fetchEntry.alive,
        fetch_via: fetchEntry.via || null, // telemetry: fetch method
        source_class: final.source_class,
        label: final.label,
        final_source: final.final_source,
        corrected_value: final.corrected_value || null, // PARTIAL: correct value from the page
        confidence: final.confidence,
        fabricated: final.fabricated,
        tier, // who rendered the final verdict: sonnet / opus / counter / deterministic
        escalated: v.escalate === true || tier === "opus" || tier === "counter",
        disagreement, // null or {sonnet, opus, sonnet_note}
        counter, // null / {overturned, quote}
        quote: final.quote || null, // verbatim excerpt for SUPPORTED/PARTIAL
        note: final.note,
      });
    }
    return groupResults;
  });
}

// Run all groups in parallel.
const groupJudgeResults =
  groupJudgePromises.length > 0 ? await parallel(groupJudgePromises) : [];

// Merge all results into one list, preserving the original claim order.
const allResults = [...deterministicResults, ...groupJudgeResults.flat()];

// Restore order according to the original claims list.
const resultById = Object.fromEntries(allResults.map((r) => [r.id, r]));
const out = claims.map((c) => resultById[c.id]).filter(Boolean);

const tally = out.reduce(
  (a, c) => ((a[c.label] = (a[c.label] || 0) + 1), a),
  {},
);
const nOpus = out.filter((c) => c.tier === "opus").length;
const nFlip = out.filter((c) => c.counter && c.counter.overturned).length;
const judgeCallCount = urlGroups.size - urlsDead; // one agent per live URL group
log(
  `Done: SUPPORTED ${tally.SUPPORTED || 0} · MISATTRIBUTED ${tally.MISATTRIBUTED || 0} · ` +
    `BROKEN_SOURCE ${tally.BROKEN_SOURCE || 0} · UNSOURCED ${tally.UNSOURCED || 0} · ` +
    `Opus used: ${nOpus}/${out.length} · counter overturned "no"→"yes": ${nFlip} · ` +
    `judge agents: ${judgeCallCount}`,
);

const result = {
  topic,
  engine,
  trust: profile.trust,
  tally,
  opus_used: nOpus,
  counter_flips: nFlip,
  claims: out,
  telemetry: {
    output_tokens: budget.spent() - spent0,
    n_claims: out.length,
    tally,
    opus_used: nOpus,
    counter_flips: nFlip,
    escalated: out.filter((c) => c.escalated).length,
    urls_total: urlsTotal,
    urls_dead: urlsDead,
    judge_calls: judgeCallCount,
  },
};

// Save verdicts to disk from within the workflow (atomize.js pattern) — the orchestrator
// does not need to move the result by hand; select_status/build_pool read from here.
// args.round (2,3,…) → suffix __rN for refinement rounds.
const roundSuffix = A.round && Number(A.round) > 1 ? `__r${A.round}` : "";
const verdictPath = `${DATA_ROOT}/topics/${topic}/verdicts/${engine}${roundSuffix}.json`;
await agent(
  `Write exactly the following JSON to file ${verdictPath} (create the folder if needed, use Bash mkdir -p). Do not change anything in the content:\n\n${JSON.stringify(result, null, 1)}`,
  { label: `save-verdicts:${engine}`, phase: "Verdict", model: "haiku" },
);
log(`verdicts saved → ${verdictPath}`);

return result;
