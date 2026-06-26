---
title: "refactor: Port engine improvements up, separate data via RESEARCH_VAULT, reorganize into a clean package"
type: refactor
date: 2026-06-26
origin: docs/brainstorms/2026-06-26-research-stack-migration-requirements.md
depth: deep
branch: feat/module-reorg-vault
worktree: ../research-factcheck-funnel-reorg
---

# refactor: Port engine improvements up + RESEARCH_VAULT separation + clean package layout

## Summary

Bring the public `research-factcheck-funnel` engine up to the state of the newer local
`research-stack`, with three guarantees: (1) every quality/gate improvement is ported up
and scrubbed of personal/client data and absolute paths; (2) all topic data reads and
writes through a single `RESEARCH_VAULT`-rooted location so the public repo ships only
`topics/example`; (3) the ported code lands in a coherent package layout (engines / gates /
selection / sources / rendering / core / orchestration), not a flat file dump.

This plan is **code-only**. Repo renames, vault repo creation, real-research migration,
local-folder archiving, and skill rewiring are explicitly out of scope (see Scope Boundaries).

**Source of truth for ported code:** the local repo at `~/Projects/personal/research-stack`
(read-only reference; never modified by this plan).

---

## Problem Frame

The public repo is an 8-day-stale snapshot. It lacks four live pipeline gates
(`citation_gate`, `relevance_gate`, `scope_gate`, `term_gate`) and several quality
utilities, and its `check_claims.js` / `run.py` / `render_paged.py` diverge substantially
from the working local versions. Separately, topic data location is half-abstracted: most
modules go through `funnel/paths.py`, but eight files hardcode `topics/<topic>` strings, and
the local source files hardcode absolute `/Users/nsolovev/...` ROOT paths that would break on
any other machine. Finally, the flat 30-file root + `funnel/` layout makes the engine hard to
read and would make the port "land as a dump." All three must be fixed together so the public
repo is provably clean, vault-driven, and tidy.

---

## Requirements

- **R1** Port up the four live gates and the quality utilities from the local source, each scrubbed of personal/client data and absolute paths (origin: requirements "Port up into public").
- **R2** Single data root: all topic I/O (Python and JS) resolves under `RESEARCH_VAULT` (default `~/research-vault`), with the public repo shipping only `topics/example`. Falls back so `funnel/run.py example` works with no vault configured.
- **R3** Reorganize the ported code into a clean package layout with explicit sub-packages, replacing the flat root + `sys.path` hacks.
- **R4** The public-leak guard (`tests/test_no_public_leaks.py` + `denylist.txt`) is extended to cover the new surface and passes.
- **R5** `python3 funnel/run.py example` (or its post-reorg equivalent) passes end-to-end; `funnel/test_funnel.py` gate tests pass.

---

## Key Technical Decisions

- **KTD1 — `paths.py` becomes the only topic-path authority, rooted at `RESEARCH_VAULT`.**
  Today `paths.py` computes `ROOT/topics/<topic>`; change `ROOT` for *data* to
  `RESEARCH_VAULT` (default `~/research-vault`), keeping `topics/example` resolvable from the
  repo as the bundled fallback when the requested topic exists in-repo but not in the vault.
  Every hardcoded `topics/` reference (5 Python, 3 JS files) is rewritten to call the
  authority. Rationale: `catalog.py`/`publish.py` already use this exact env var — extend the
  pattern rather than invent a new one.

- **KTD2 — JS path contract via a single resolver, fed by env, not hardcoded ROOT.**
  `check_claims.js`, `atomize.js`, `resource.js`, `clarity_audit.js` currently build
  `${ROOT}/topics/...`. Replace the hardcoded `const ROOT = "/Users/..."` with resolution
  from `process.env.RESEARCH_STACK_ROOT` (repo root, for the engine) and
  `process.env.RESEARCH_VAULT` (data root), mirroring the Python authority. A tiny shared
  `js/paths.js` helper is the JS counterpart to `paths.py`.

- **KTD3 — Package layout: convert flat repo to an installable package, sub-packaged by role.**
  Introduce `pyproject.toml` and group modules (see Output Structure). Behavior-preserving:
  same functions, new import paths, `__init__.py` re-exports so `run.py` stage order is
  unchanged. Done **last**, after behavior is locked by R2/R5, so the reorg is a mechanical
  move on a green codebase.

- **KTD4 — Scrub at port time, not after.** Each ported file is cleaned on the way in:
  absolute `/Users/` ROOTs → resolver; byline "Никита Соловьёв" (`render_paged.py:1224`) →
  configurable `author` field defaulting to a generic label; "Futura" example comment →
  neutral placeholder. The leak test (R4) is the backstop.

- **KTD5 — Standalone utilities ported but kept out of the live `run.py` chain.**
  `preflight.py`, `merge_recovered.py`, `wf_watchdog.py`, `clarity_audit.js` are ported as
  tools; `migrate_topics.py` is ported only if it helps vault migration, else left in the
  local repo. The four gates (`citation/relevance/scope/term`) ARE wired into the orchestrator
  exactly as in the local `run.py`.

---

## Output Structure

Target layout after KTD3 (illustrative; implementer may refine):

```
research-stack/                 # repo (renamed later, out of scope)
  pyproject.toml                # NEW: installable package
  research_stack/               # NEW package root (was flat root + funnel/)
    __init__.py
    core/                       # paths, contracts, step, receipts, telemetry, budget
    engines/                    # engines.py, preflight_engines.py, preflight.py
    gates/                      # gate, sync_gate, prose_gate, citation_gate,
                                #   relevance_gate, scope_gate, term_gate
    selection/                  # build_pool, select_by_source, select_status,
                                #   audit_rejected, merge_recovered, coverage_audit
    sources/                    # enrich_sources, resolve_oa, archive_evidence, prefetch
    rendering/                  # render_final, render_paged, set_single_page,
                                #   stamp_narratives, stamp_clarity
    orchestration/              # run, doctor, catalog, publish, scaffold_config,
                                #   engine_status, engine status helpers
    js/                         # atomize.js, check_claims.js, resource.js,
                                #   clarity_audit.js, deep-research-cheap.js, paths.js
    tools/                      # wf_watchdog.py, (migrate_topics.py)
  topics/example/               # only bundled topic
  tests/                        # test_funnel.py, test_no_public_leaks.py, denylist.txt
  docs/
```

---

## Implementation Units

### U1. Centralize the data root in `paths.py` on `RESEARCH_VAULT`

**Goal:** One authority computes every `topics/<topic>/...` path under `RESEARCH_VAULT`, with `topics/example` resolvable in-repo as fallback.
**Requirements:** R2.
**Dependencies:** none.
**Files:** `funnel/paths.py`, `funnel/test_funnel.py` (add path-resolution tests).
**Approach:** Add a `topics_root()` that returns `RESEARCH_VAULT/topics` when set or when the topic exists there, else the in-repo `topics/` (so bundled `example` works with no vault). Keep all existing `P.*` accessors; they now derive from `topics_root()`. Document the precedence in the module docstring.
**Patterns to follow:** existing `RESEARCH_VAULT` read in `funnel/catalog.py:19`, `funnel/publish.py:23`.
**Test scenarios:**
- Happy path: `RESEARCH_VAULT` unset → `P.pool("example")` resolves under repo `topics/example`.
- Vault set, topic present in vault → resolves under `$RESEARCH_VAULT/topics/<topic>`.
- Vault set, topic absent in vault but present in repo (`example`) → falls back to repo copy.
- Edge: `RESEARCH_VAULT` set to a non-existent dir → clear error, not silent repo write.
**Verification:** `funnel/run.py example` still completes; new path tests pass.

### U2. Route the five hardcoded-path Python modules through `paths.py`

**Goal:** Remove every direct `os.path.join(ROOT, "topics", ...)` in Python.
**Requirements:** R2.
**Dependencies:** U1.
**Files:** `funnel/select_by_source.py`, `funnel/stamp_narratives.py`, `funnel/stamp_clarity.py`, `funnel/coverage_audit.py`, `funnel/sync_gate.py`.
**Approach:** Replace literal joins (`select_by_source.py:69,138`; `stamp_narratives.py:21,26`; `stamp_clarity.py:21,28`; `coverage_audit.py:59,70`; `sync_gate.py:27`) with `P.*` calls. No behavior change.
**Patterns to follow:** how `contracts.py` / `build_pool.py` already call `P.*`.
**Test scenarios:**
- Each module produces byte-identical output paths before/after for `example` (characterization).
- With `RESEARCH_VAULT` set, each writes under the vault, not the repo.
**Execution note:** Add characterization coverage on `example` before refactoring these.
**Verification:** gate tests + a full `example` run unchanged.

### U3. JS path resolver — replace hardcoded absolute ROOTs

**Goal:** JS engine files resolve repo-root and data-root from env, not a hardcoded `/Users/...` string.
**Requirements:** R1, R2.
**Dependencies:** U1.
**Files:** `js/paths.js` (new), `check_claims.js`, `atomize.js`, `resource.js`.
**Approach:** New `js/paths.js` reads `RESEARCH_STACK_ROOT` (default: resolve from `__dirname`) and `RESEARCH_VAULT` (default `~/research-vault`), exposing `topicDir(topic)`, `engines(topic)`, etc., matching `paths.py` semantics. Rewrite the hardcoded `const ROOT = "/Users/..."` (`check_claims.js:39`, and the local `clarity_audit.js:21` when ported in U5) and the `${ROOT}/topics/...` joins to use it.
**Patterns to follow:** `paths.py` accessor names so Python and JS stay symmetric.
**Test scenarios:**
- `check_claims.js` on `example` writes verdicts to the same place as before when no env set.
- With `RESEARCH_VAULT` set, verdicts land under the vault.
- Repo contains no `/Users/` absolute path after this unit (grep asserts none).
**Verification:** atomize → check_claims → run chain on `example` produces a report.

### U4. Port the four live gates and wire them into the orchestrator

**Goal:** `citation_gate`, `relevance_gate`, `scope_gate`, `term_gate` exist in the public repo and run in `run.py` exactly as in the local source.
**Requirements:** R1, R5.
**Dependencies:** U1, U2.
**Files:** `funnel/citation_gate.py`, `funnel/relevance_gate.py`, `funnel/scope_gate.py`, `funnel/term_gate.py` (new, ported), `funnel/run.py` (wire stages), `funnel/test_funnel.py` (gate tests for each).
**Approach:** Copy from local `research-stack/funnel/*`, swap any `topics/` access to `P.*` (U1), and insert the stages into `run.py` at the positions used in the local orchestrator (local run.py: relevance ~L88, term ~L124, scope ~L134 `--hard`, citation ~L129). `scope_gate` doubles as a personal-context-leak guard — keep it. Reconcile the diverged public `run.py`/`gate.py` against the local versions as part of this unit.
**Patterns to follow:** existing `gate.py` hard-gate structure; local `run.py` stage ordering.
**Test scenarios:**
- citation: a fact whose prose href doesn't match its pool source URL → build killed.
- relevance: an off-topic fact flagged by verdict → excluded from pool.
- scope: a question/fact carrying a personal-context marker → hard-fail (or flagged) as designed.
- term: a jargon term used before its first-mention explanation → build killed.
- Integration: all four wired in `run.py` run in order on `example` without false-positive killing the clean example.
**Verification:** `run.py example` passes with all four gates active; each gate's negative test fails the build as expected.

### U5. Port the quality utilities (scrubbed), kept out of the live chain

**Goal:** `clarity_audit.js`, `preflight.py`, `merge_recovered.py`, `wf_watchdog.py` available as tools; `set_single_page.py` and the diverged `render_paged.py` / `atomize.js` / `check_claims.js` brought up to local state.
**Requirements:** R1, KTD4, KTD5.
**Dependencies:** U3.
**Files:** `funnel/preflight.py`, `funnel/merge_recovered.py`, `funnel/wf_watchdog.py`, `js/clarity_audit.js`, `set_single_page.py`, `render_paged.py`, `atomize.js`, `check_claims.js`.
**Approach:** Port each from local; scrub at port time per KTD4 — fix `clarity_audit.js:21` ROOT, `check_claims.js:39` ROOT (via U3 resolver), `render_paged.py:1224` byline → configurable `author` (default generic), `render_paged.py:654` "Futura" comment → neutral. `migrate_topics.py` ported only if it aids U-side vault migration; otherwise note as left-behind.
**Test scenarios:**
- `render_paged.py` with no `author` config → generic byline, not a personal name.
- `clarity_audit.js` runs on `example` narratives without an absolute-path crash.
- Repo grep for "Futura", "Никита", "/Users/" returns nothing in shipped code.
**Verification:** rendered `example` report carries no personal/client data; leak test (U7) passes.

### U6. Reorganize into the package layout

**Goal:** Flat root + `funnel/` → `research_stack/` package with role sub-packages and `pyproject.toml`; `sys.path` hacks removed.
**Requirements:** R3.
**Dependencies:** U1–U5 (behavior locked first).
**Files:** new `pyproject.toml`, new `research_stack/**` tree (see Output Structure), every moved module's imports, `funnel/run.py` entry point (becomes `research_stack.orchestration.run` with a thin `funnel/run.py` or console-script shim for back-compat), `tests/` import updates.
**Approach:** Mechanical move + import rewrite. Add `__init__.py` re-exports so call sites and the orchestrator stage order are unchanged. Provide a console-script entry (e.g. `research-stack-run`) and keep a thin `funnel/run.py` shim so `python3 funnel/run.py example` still works (R5). No logic edits in this unit.
**Patterns to follow:** standard `src`-less package with `pyproject.toml`; existing module groupings from the import-graph clusters (paths→core, gates cluster, etc.).
**Test scenarios:**
- `pip install -e .` succeeds; `from research_stack.core import paths` imports.
- `funnel/run.py example` (shim) and the console script both run the full chain.
- `funnel/test_funnel.py` passes unchanged in behavior after import updates.
**Execution note:** Land as one mechanical commit after the suite is green on U1–U5.
**Verification:** full `example` run + both test files pass post-move.

### U7. Extend and run the public-leak guard

**Goal:** The leak test covers the new ported surface and passes; `topics/` ships only `example`.
**Requirements:** R4, R2.
**Dependencies:** U4, U5, U6.
**Files:** `tests/test_no_public_leaks.py`, `denylist.txt`, `.gitignore`.
**Approach:** Add denylist tokens ("Никита", "Соловьёв", "Futura", `/Users/nsolovev`, `personal_profile`) and assert no `topics/*` other than `example` is tracked. Ensure `.gitignore` excludes `$RESEARCH_VAULT` artifacts and any stray `topics/<real>`.
**Test scenarios:**
- A planted forbidden token anywhere in tracked files → test fails.
- A tracked `topics/realtopic/` → test fails.
- Clean tree → test passes.
**Verification:** `pytest tests/test_no_public_leaks.py` green; `git ls-files topics/` lists only `example`.

---

## Scope Boundaries

### Deferred to Follow-Up Work (this repo, later PRs)
- README / PIPELINE.md rewrite to document `RESEARCH_VAULT` setup for new users.

### Outside this product's identity (manual, user-run, irreversible — NOT in this plan)
- GitHub repo renames (`research-stack` legacy → `research-stack-legacy`; `research-factcheck-funnel` → `research-stack`).
- Creating the private `research-vault` repo and migrating the 21 real topics / 56 reports / `personal_profile.json` into it.
- Archiving the old local folders (`research-stack`, `research-stack-cm-final`).
- Rewiring `~/.claude` `/research` and `/deep-research` skills to the public engine + vault.

---

## Risks & Dependencies

- **Reorg breaks the JS↔Python path contract.** The JS files write artifacts the Python stages read by path. Mitigation: U3 lands the JS resolver with symmetric semantics *before* U6 moves anything; characterization tests on `example` guard the contract.
- **`run.py` divergence.** Public and local `run.py` differ by ~97 lines; blindly copying could drop public-only fixes. Mitigation: U4 reconciles rather than overwrites — diff both, keep the union of correct behavior.
- **Hidden personal data in ported files beyond the known hits.** Mitigation: U7 leak test is the structural backstop, run before any push.
- **Vault fallback ambiguity.** If a real topic name collides with `example`, fallback could read the wrong copy. Mitigation: U1 precedence is explicit (vault wins when present); only `example` is bundled.

---

## Success Criteria

- `python3 funnel/run.py example` passes end-to-end (R5).
- `pytest funnel/test_funnel.py tests/test_no_public_leaks.py` green (R4, R5).
- `git grep -nE "Futura|Никита|Соловьёв|/Users/nsolovev|personal_profile"` over tracked files returns nothing (R1, R4).
- A run with `RESEARCH_VAULT=/tmp/rv` writes all topic artifacts under `/tmp/rv`, nothing under the repo (R2).
- `from research_stack.core import paths` works after `pip install -e .` (R3).
