"use strict";
// Single source of funnel paths for the JS engine files — mirrors funnel/paths.py.
//
// Layout: topics/<topic>/ holds question.txt, facts.json, engines/<engine>.json,
// atoms/<engine>.json, verdicts/<engine>[__rN].json, pool*.json, narratives.json,
// config.json, evidence/, manifest.json, …
//
// Two roots:
//   • repo/engine root  — where the scripts (prefetch.py, fetch_url.sh, …) live.
//     RESEARCH_STACK_ROOT overrides it; default is the parent of this js/ dir.
//   • data root         — RESEARCH_VAULT. When set, real research topics live
//     there so the public repo keeps only the bundled topics/example.
//
// topics_root_for() precedence matches paths.py exactly:
//   1. RESEARCH_VAULT unset          -> repo topics/ (bundled example)
//   2. vault set, topic in vault      -> $RESEARCH_VAULT/topics
//   3. vault set, topic only in repo  -> repo topics/ (bundled example)
//   4. vault set, topic in neither    -> $RESEARCH_VAULT/topics (new topic)
const path = require("path");
const fs = require("fs");
const os = require("os");

function expand(p) {
  if (!p) return p;
  if (p === "~") return os.homedir();
  if (p.startsWith("~/")) return path.join(os.homedir(), p.slice(2));
  return p;
}

// Repo/engine root holds the bundled `topics/example` only.
const REPO_ROOT = process.env.RESEARCH_STACK_ROOT
  ? path.resolve(expand(process.env.RESEARCH_STACK_ROOT))
  : path.resolve(__dirname, "..");
const ROOT = REPO_ROOT; // back-compat alias for callers that referenced ROOT

// ── data root resolution (RESEARCH_VAULT) ───────────────────────────────────
function vaultRoot() {
  // Return the configured vault root, or null when RESEARCH_VAULT is unset.
  // A RESEARCH_VAULT pointing at a missing directory is an error rather than a
  // silent fall-through to a repo write.
  const v = process.env.RESEARCH_VAULT;
  if (!v) return null;
  const p = path.resolve(expand(v));
  if (!fs.existsSync(p)) {
    throw new Error(`RESEARCH_VAULT points to a non-existent directory: ${p}`);
  }
  return p;
}

function topicsRootFor(topic) {
  const vault = vaultRoot();
  if (vault === null) return path.join(REPO_ROOT, "topics");
  if (fs.existsSync(path.join(vault, "topics", topic))) {
    return path.join(vault, "topics");
  }
  if (fs.existsSync(path.join(REPO_ROOT, "topics", topic))) {
    return path.join(REPO_ROOT, "topics");
  }
  return path.join(vault, "topics");
}

// ── topic directory ─────────────────────────────────────────────────────────
function topicDir(topic) {
  return path.join(topicsRootFor(topic), topic);
}

// ── topic input data ────────────────────────────────────────────────────────
function question(topic) {
  return path.join(topicDir(topic), "question.txt");
}
function facts(topic) {
  return path.join(topicDir(topic), "facts.json");
}

// ── raw engine output ───────────────────────────────────────────────────────
function enginesDir(topic) {
  return path.join(topicDir(topic), "engines");
}
function engineRaw(topic, engine) {
  return path.join(enginesDir(topic), `${engine}.json`);
}

// ── atoms ───────────────────────────────────────────────────────────────────
function atomsDir(topic) {
  return path.join(topicDir(topic), "atoms");
}
function atoms(topic, engine) {
  return path.join(atomsDir(topic), `${engine}.json`);
}

// ── selection ───────────────────────────────────────────────────────────────
function selection(topic) {
  return path.join(topicDir(topic), "selection.json");
}
function selectBySource(topic) {
  return path.join(topicDir(topic), "select_by_source.json");
}

// ── verdicts ────────────────────────────────────────────────────────────────
function verdictsDir(topic) {
  return path.join(topicDir(topic), "verdicts");
}
function verdict(topic, engine, round) {
  const suffix = round && Number(round) > 1 ? `__r${round}` : "";
  return path.join(verdictsDir(topic), `${engine}${suffix}.json`);
}

// ── fact pool ───────────────────────────────────────────────────────────────
function pool(topic) {
  return path.join(topicDir(topic), "pool.json");
}
function poolRaw(topic) {
  return path.join(topicDir(topic), "pool_raw.json");
}
function poolResourced(topic) {
  return path.join(topicDir(topic), "pool_resourced.json");
}
function sections(topic) {
  return path.join(topicDir(topic), "sections.json");
}
function contradictions(topic) {
  return path.join(topicDir(topic), "contradictions.json");
}

// ── audit ───────────────────────────────────────────────────────────────────
function audit(topic) {
  return path.join(topicDir(topic), "audit_rejected.json");
}

// ── layout (narratives + config) ────────────────────────────────────────────
function narratives(topic) {
  return path.join(topicDir(topic), "narratives.json");
}
function narrativesLock(topic) {
  return path.join(topicDir(topic), "narratives.lock");
}
function config(topic) {
  return path.join(topicDir(topic), "config.json");
}
function clarityLock(topic) {
  return path.join(topicDir(topic), "clarity.lock");
}
function clarityFindings(topic) {
  return path.join(topicDir(topic), "clarity_findings.json");
}

// ── run artifacts ───────────────────────────────────────────────────────────
function evidenceDir(topic) {
  return path.join(topicDir(topic), "evidence");
}
function manifest(topic) {
  return path.join(topicDir(topic), "manifest.json");
}

module.exports = {
  ROOT,
  REPO_ROOT,
  topicsRootFor,
  topicDir,
  question,
  facts,
  enginesDir,
  engines: enginesDir, // alias matching the paths.py accessor shorthand
  engineRaw,
  atomsDir,
  atoms,
  selection,
  selectBySource,
  verdictsDir,
  verdict,
  pool,
  poolRaw,
  poolResourced,
  sections,
  contradictions,
  audit,
  narratives,
  narrativesLock,
  config,
  clarityLock,
  clarityFindings,
  evidenceDir,
  manifest,
};
