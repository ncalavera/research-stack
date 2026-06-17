# funnel/ — deterministic core of the fact-check funnel with gates

Final set. This is where scripts that require no model live; they assemble the report from
verdicts under strict gates. Agentic tools (engines, fact-checking, re-sourcing)
and the swappable renderer live in the repository root — see "What's Where".

## Running

```bash
python3 funnel/run.py <topic> ["Report Title"]   # full tail with gates
python3 funnel/test_funnel.py                     # gate tests (10 checks)
python3 funnel/gate.py <topic>                    # guard only (exit 1 = printing blocked)
```

`topic` — any slug: `topic1`, `work-pricing`, `churn-q3`. Data is read/written from
`topics/<topic>/` (new layout); scripts locate the root themselves via `funnel/paths.py`.

## Stage Order (single source of truth — `run.py`)

| # | Stage | Script | Gate Before | Gate After |
|---|-------|--------|-------------|------------|
| 1 | pool (+re-sourcing) | `build_pool.py` | engine verdicts exist | raw and pool valid |
| 2 | audit | `audit_rejected.py` | raw valid | audit valid |
| 3 | sources | `enrich_sources.py` | pool valid | sources have names |
| 4 | layout | `scaffold_config.py` | — | config valid |
| 5 | **GUARD** | `gate.py` | — | **every fact has a verified anchor = text** |
| 6 | print | `../render_final.py` | config valid | report created and non-empty |
| 7 | PDF (soft) | `../render_pdf.sh` | — | no Chrome → warning |
| 8 | wiki (`--publish`) | `publish.py` | — | no vault → skip |
| 9 | telemetry (soft) | `telemetry.py` | — | artifacts → `telemetry/ledger.jsonl` |

Re-sourcing is merged INSIDE `build_pool` (a restored live source becomes an anchor
for a previously dead fact). Fact sections are edited in sidecar `pool/<topic>.sections.json`
by `fid` — fact text is never edited, otherwise the guard will reject it. Clarification: verdicts
from a new round are files `<engine>__rN.json`; build_pool keys by filename and merges them into the pool
(the first run is not lost). `--publish` places report+PDF+`index.md` into `vault/library/research/<domain>/<topic>/`.

The first failed gate stops the chain with a clear message. Printing stands AFTER
the guard — so an unconfirmed fact physically cannot reach the report.

## Guard Guarantee (`contracts.offenders_in`)

**Text→verified source binding.** Only what the judge verified on a live
source in exactly this wording may be printed. A fact carries text VERBATIM equal to one of its claims —
the "anchor". Anchor ⟺ verdict SUPPORTED/PARTIAL, link is an http(s) URL, `source_alive is true`, not
fabricated, and the number is not corrected (`corrected` is empty — otherwise the source confirms a different value).

**Hard gate (blocks printing).** A fact is valid ⟺ `best_source` is a URL, and the provenance contains an
anchor whose `text` verbatim matches the fact's `text`. The `is_anchor` flag is recalculated by the guard itself;
the stored value is not trusted. Catches: text rewritten after fact-check under a foreign link, merging
different claims, dead/fake/fabricated source, corrected number, restored fact without flags.

**Soft signal (warns, does not block).** Traceability: fact sources are cross-checked against
verdict and re-sourcing sources. If none match — "check manually". Not a block: Opus
legitimately changes only sections, and re-sourcing brings new sources.

Tests (`test_funnel.py`, 18 checks) catch every bypass scenario, including rewritten
text under a live link and a corrected number. Found by two audits (Claude + Codex) and closed.

## Files

- `run.py` — orchestrator: stage order + gates, stops at first error.
- `contracts.py` — shapes of all artifacts + input/output checks + guard core.
- `gate.py` — hard guard before printing (CLI).
- `build_pool.py` — verdicts (+re-sourcing) → `topics/<topic>/pool_raw.json` + `topics/<topic>/pool.json`, fact→anchor binding, rebuilt each run.
- `audit_rejected.py` — audit of fairness of rejected facts.
- `enrich_sources.py` — source names and years into the pool.
- `scaffold_config.py` — minimal layout config for a new topic.
- `publish.py` — publish report to wiki: `vault/library/research/<domain>/<topic>/` (HTML + PDF + `index.md` card). Pass `--domain <ai|career|…>`; without the flag — goes to `_inbox`.
- `test_funnel.py` — gate tests (18 checks).
- `telemetry.py` — run telemetry: reads topic artifacts and appends one line to `telemetry/ledger.jsonl` (soft stage).
- `archive_evidence.py` — archives topic source pages: collects URLs from verdicts, copies cache gzip-compressed to `topics/<topic>/evidence/`, maintains `index.json`. With `--manifest --mode light|deep` adds a round entry to `topics/<topic>/manifest.json`.
- `catalog.py` — catalog generator: scans all topics, writes `catalog.json` and `CATALOG.md` to the repository root. Runs as a soft stage after each `run.py` run.

## What's Where (why not everything in one folder)

Parts with external coupling stay in the root — moving them would silently break things:
- `render_final.py` — renderer, separately reworked for PDF/HTML. The funnel calls it as a swappable module.
- `engines.py`, `check_claims.js`, `resource.js`, `deep-research-cheap.js` — agentic stages (called by the `/research` skill); JS tools have names in the registry and relative calls to `./resolve_oa.py`, `./fetch_url.sh`.

Full architecture and path contract — in `../PIPELINE.md`. Run the full chain with one
request — skill `/research <question> --deep`.
