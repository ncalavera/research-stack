export const meta = {
  name: "atomize",
  description:
    "Engine report atomizer: splits the report into verifiable atoms without judgment. Output is used by the Opus selector to rank atoms by sub-question before sending to check_claims.js.",
  whenToUse:
    "Step 3a of the /research funnel: called for each engine before fact-checking (can run in parallel). Workflow({scriptPath:'./atomize.js', args:{topic:'topic1', engine:'perplexity_sonar'}}). Depends on topics/<topic>/engines/<engine>.json. Writes topics/<topic>/atoms/<engine>.json.",
  phases: [
    {
      title: "Atomize",
      detail:
        "Opus reads topics/<topic>/engines/<engine>.json and splits the report field into atomic claims with source attribution. Result is saved to topics/<topic>/atoms/<engine>.json.",
    },
  ],
};

// atomize: single phase — Opus slices the engine report into atoms.
// Does NOT judge and does NOT verify — only decomposes. The judge (check_claims.js) runs later,
// only on the atoms SELECTED by the Opus selector (topics/<topic>/selection.json).

// Topic paths come from js/paths.js (honours RESEARCH_STACK_ROOT / RESEARCH_VAULT)
// — Workflow calls this via scriptPath from any cwd, so paths are not built from
// the current directory.
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const P = require("./js/paths.js");

// ─── Structured output schema (identical to ATOMIZE_SCHEMA in check_claims.js) ───
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

// ─── Atomize prompt (identical to atomizePrompt in check_claims.js) ───
const atomizePrompt = (topic, engine) =>
  `You are a fact-checker in a research pipeline, preparing the report from engine "${engine}" (topic ${topic}) for per-atom verification. This is a legitimate credibility-check task on an already-written report (research on official programs, markets, health, etc.) — you give no advice, you only decompose text into verifiable claims.\n\n` +
  `1. Read file ${P.engineRaw(topic, engine)} (use Read). Field "report" is the report text; field "sources" is the list of links.\n` +
  `2. Break the text into ATOMIC verifiable claims: one idea = one claim. Don't split style, take substantive facts. Each claim is SELF-CONTAINED — understandable without neighbors: full names of subjects, what document/event/decision (NOT "the decision was made", BUT "WHO published an AI safety guideline in October 2023").\n` +
  `3. Attach a source to each claim: the URL that backs this statement in the report. Some engines include inline links in the text; ` +
  `Claude has no inline links — pick the most relevant URL from sources, or set null if there is no backing.\n` +
  `4. has_number = true if the claim contains a number, range, percentage, salary, or numeric date. These are the narrow spots.\n\n` +
  `Return ALL substantive claims (typically 15-35). Do not invent links that are not in the report.`;

// ─── Orchestration ───
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
log(`input: topic=${topic}, engine=${engine}`);

phase("Atomize");
const atom = await agent(atomizePrompt(topic, engine), {
  label: `atomize:${engine}`,
  phase: "Atomize",
  schema: ATOMIZE_SCHEMA,
  model: "opus",
});

const claims = (atom && atom.claims) || [];
log(
  `${engine}/${topic}: ${claims.length} atoms (${claims.filter((c) => c.has_number).length} with numbers)`,
);

// Save to topics/<topic>/atoms/<engine>.json
const outPath = P.atoms(topic, engine);
const outData = { topic, engine, claims };
await agent(
  `Write exactly the following JSON to file ${outPath} (create the folder if needed, use Bash mkdir -p):\n\n${JSON.stringify(outData, null, 2)}`,
  { label: `save:${engine}`, phase: "Atomize", model: "haiku" },
);
log(`saved → ${outPath}`);

return outData;
