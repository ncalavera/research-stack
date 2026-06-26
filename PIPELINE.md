# Fact-Check Funnel — Architecture

One topic, one run, one report. Guarantee: no fact reaches the report without a live confirmed source. Entry point — `/research <question> --deep`.

## Contract (one logic for any topic)

`topic` — any slug (`topic1`, `work-pricing`, `churn-q3`). Each step is `<script> <topic>`, reading and writing to fixed paths. The `topics/<topic>/` root below is resolved by `funnel/paths.py`: when `RESEARCH_VAULT` is set it lives at `$RESEARCH_VAULT/topics/<topic>/` (the vault owns all reads and writes); when unset it falls back to the repo's `topics/` — i.e. the bundled `topics/example` demo. So the same paths point at private data in normal use and at the shipped example with no setup. See [README → Data location](README.md#data-location--research_vault).

```
topics/<topic>/question.txt                  full question for the engines
topics/<topic>/facts.json                    sub-questions for the topic
topics/<topic>/engines/<engine>.json         raw engine output (report + sources)
topics/<topic>/atoms/<engine>.json           atoms after atomize.js (no verdict)
topics/<topic>/selection.json                Opus selection: ranked + verified per qid
topics/<topic>/verdicts/<engine>.json        per-verdict fact-check (rounds — __rN)
topics/<topic>/pool_raw.json                 flat: confirmed / unconfirmed
topics/<topic>/pool.json                     facts with provenance (render input)
topics/<topic>/contradictions.json           discrepancies: {groups:[{gid,issue,fids,note}]} (opt., step 5)
topics/<topic>/pool_resourced.json           result of re-sourcing (opt.)
topics/<topic>/audit_rejected.json           audit of rejected facts
topics/<topic>/config.json                   layout: title, sections, footer
topics/<topic>/narratives.json               prose per section (opt.)
topics/<topic>/evidence/                     archive of source pages
topics/<topic>/manifest.json                 round log for the topic
reports/REPORT-<topic>.html                  output (renderer — always in the repo's reports/)
```

(`topics/<topic>/` resolves under `$RESEARCH_VAULT` when set — see the note above.)

Add a topic = create `facts.json` + `question.txt` in the topic directory (`$RESEARCH_VAULT/topics/<topic>/` with a vault, else `topics/<topic>/`). Everything else the scripts create automatically.

## Stages

| # | Stage | Tool | Type | Input → Output |
|---|-------|------|------|----------------|
| 1 | Question | Opus (skill) | LLM | `$ARGUMENTS` → `topics/<topic>/facts.json`, `topics/<topic>/question.txt` |
| 2 | Engines | `engines.py` + `deep-research-cheap.js` | script + Workflow | question → `topics/<topic>/engines/<engine>.json` |
| 3a | Atomization | `atomize.js` | Workflow (per engine, parallel) | engine report → `topics/<topic>/atoms/<engine>.json` |
| 3b | Selection | Opus (skill) | LLM | all atoms + `topics/<topic>/facts.json` → `topics/<topic>/selection.json` |
| 3c | Verification of selected | `check_claims.js` + `funnel/select_status.py` | Workflow + script (loop) | selection → `topics/<topic>/verdicts/<engine>[__rN].json` |
| 4 | Pool (+re-sourcing) | `funnel/build_pool.py` | script | verdicts + `_resourced` → `topics/<topic>/pool{_raw,}.json`, fact↔anchor, rebuilt each run |
| 5 | Sections + discrepancies | Opus (skill) | LLM | writes sidecar `topics/<topic>/sections.json` (`fid→section`) and if discrepancies exist — `topics/<topic>/contradictions.json`; does NOT edit fact text |
| 6 | Audit | `funnel/audit_rejected.py` | script | `_raw` → `topics/<topic>/audit_rejected.json` |
| 7 | Re-sourcing | `resource-facts` | Workflow | anchor-less candidates → `topics/<topic>/pool_resourced.json` (with `quote`); merged in step 4 |
| 8 | Sources | `funnel/enrich_sources.py` | script | pool → pool (+`source_meta.json`) |
| 9 | Layout | `funnel/scaffold_config.py` + Opus | script + LLM | pool → `topics/<topic>/config.json`, `topics/<topic>/narratives.json` |
| — | **GUARD** | `funnel/gate.py` | gate | blocks if a fact has no anchor with verbatim matching text |
| 10 | Render | `render_final.py` | script (swappable) | pool+config+prose → `REPORT-<topic>.html` |
| 11 | Telemetry | `funnel/telemetry.py` | script (soft) | topic artifacts → `telemetry/ledger.jsonl` (one line) |

Stages 4, 6, 8, 9 are in `funnel/`. Details — `funnel/README.md`.

## Two Orchestrators

- **`/research <question> --deep`** — full chain; agentic steps (2/3/5/7/9) are driven by an external research skill (agentic chain is driven by an external research skill).
- **`python3 funnel/run.py <topic> ["Title"]`** — deterministic tail (4→6→8→9→GUARD→10) with gates between stages. Pool is rebuilt each run (no drift). Stops at the first failed gate.

## Gates (why you cannot break the order or sneak in a lie)

Before each stage — input check, after — output check (`funnel/contracts.py`). Stage N
cannot run without a valid result from N−1: the orchestrator kills the chain with a clear message.

The hard guard (`funnel/gate.py`) before printing requires **text→source binding**: every
fact must have an "anchor" — a claim verified by the judge on a live URL (SUPPORTED/PARTIAL,
`source_alive`, not fabricated, number not corrected), whose text VERBATIM matches the fact's text.
Only the verified wording may be printed — rewritten text, a merge of different claims,
a dead/fake source all get rejected. Fact text is never edited anywhere (sections go into a
sidecar by `fid`); the pool is entirely derived from verdicts and rebuilt each run. Printing
comes AFTER the guard. Tests: `python3 funnel/test_funnel.py` (18 checks, including rewritten text
under a live URL and a corrected number).

## Principles

1. **Gates, not engine.** Every engine hallucinates. The guarantee comes from atom-level fact-checking with honest fetch (UA → r.jina.ai → Firecrawl) and a guard before printing — not from picking the "best" engine.
2. **Deterministic separated from LLM.** Scripts handle mechanics (merge, audit, render). LLM handles meaning (questions, sections, re-sourcing, prose). build_pool does a conservative text-based merge; cross-language and semantic alignment is handled by step 5.
3. **Renderer is a swappable module.** `render_final.py` reads pool+config and outputs HTML/PDF. Design changes independently of the funnel.
4. **Idempotency.** `build_pool` writes `pool.json` only if it is absent (`--force` to recreate the draft); `enrich_sources` does not create duplicates. The tail can be re-run.
5. **We verify only what goes into the report.** Stage 3b (Opus selection) separates "not selected" from "rejected": not-selected means the atom did not rank high enough for the given question — not that it is false. The audit (`judge_claims/audit/`) distinguishes this — not-selected is not counted as rejected. The reserve list (`ranked` beyond the initial `verified`) closes gaps: if the top atom is not confirmed (~36% by statistics), `select_status.py` automatically promotes the next candidate to next_batch — verification goes deeper until the question is covered or the list is exhausted. Result: cheaper with the same coverage guarantees.

## Storage and Catalog

- **`topics/<topic>/evidence/`** — permanent archive of source pages. Every URL from the topic's verdicts is saved gzip-compressed (`<sha1>.txt.gz`); `index.json` alongside stores url→{file, sha1, bytes_raw, archived_at}. Populated via `funnel/archive_evidence.py <topic>` (soft stage after telemetry). Idempotent: an already-archived file is skipped. The `evidence/` directory is committed to git.
- **`topics/<topic>/manifest.json`** — topic round log: `{rounds: [{ts, mode, engines, question_file, git_sha}]}`. Add a record: `funnel/archive_evidence.py <topic> --manifest --mode light|deep`. One call = one entry in `rounds`.
- **`CATALOG.md`** — human-readable table of all topics (date, question, engines, facts, link to report, published, % archived sources). Regenerated automatically at each `run.py` run. Source: `catalog.json`.
- **`.fetch_cache/`** — temporary cache of raw pages (ignored by git). `evidence/` — permanent archive after the run (in git). Difference: cache can be cleared without losing reproducibility; archive cannot.

## What's in the Funnel, What's Legacy

**Deterministic core — `funnel/`:** `run.py`, `contracts.py`, `gate.py`, `build_pool.py`, `audit_rejected.py`, `enrich_sources.py`, `scaffold_config.py`, `test_funnel.py`.

**Agentic tools and renderer — in root** (external coupling; moving them would silently break things): `engines.py`, `check_claims.js`, `resource.js`, `deep-research-cheap.js`, `resolve_oa.py`, `fetch_url.sh`, `render_final.py`, `render_paged.py`.

Hard guard before printing — `funnel/gate.py`.

## Extension Contracts

- **`quote` in verdict/pool** — `check_claims.js` verdict carries a `quote` field (MANDATORY for SUPPORTED/PARTIAL: verbatim quote of the decisive source fragment; null for MISATTRIBUTED/BROKEN_SOURCE/UNSOURCED). `build_pool.to_item`/`to_fact` pass it into the fact and provenance. The renderer shows a "what the source says" fold-out next to the fact card.
- **`stances` in contradictions.json** — optional dict `{fid: "supports"|"refutes"|"mixed"}` in each group in `contradictions.json`; the renderer shows ▲/▼/◆ chips next to the fact card inside the "⚡ Sources disagree" block.
