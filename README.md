# research-factcheck-funnel

A deep-research pipeline with a **fact-check gate**: no claim reaches the final
report without a live, verified source backing that exact wording. The guarantee
is structural, not a matter of trust — a hard gate sits before rendering and
physically refuses to print anything whose text isn't anchored to a checked source.

The problem this solves: every research engine (Perplexity, Gemini grounded,
OpenAI deep research, Exa, …) hallucinates some fraction of its claims and cites
sources that don't actually say what's attributed to them. Picking the "best"
engine doesn't fix this. A gate does.

## The guarantee

A fact may be printed only if it carries an **anchor**: a claim a judge verified
against a live URL (`SUPPORTED`/`PARTIAL`, `source_alive == true`, not fabricated,
no edited number) whose text is **verbatim equal** to the fact's text. The gate
recomputes the anchor flag itself and trusts nothing recorded upstream. This blocks:

- text rewritten after fact-checking and slipped under an unrelated link,
- two different claims merged into one,
- dead / fake / fabricated sources,
- an edited number under a source that supports a different value.

Fact text is never edited anywhere downstream (sections are stored in a sidecar by
`fid`); the pool is derived entirely from verdicts and rebuilt on every run, so the
gate can't be desynced. Rendering runs **after** the gate. The bypass scenarios are
each covered by `funnel/test_funnel.py`.

## Pipeline

One topic, one run, one report. `topic` is any slug; every step reads and writes
under fixed paths in `topics/<topic>/`. Two orchestrators:

- **Agentic chain** (driven by an LLM skill): question → engines → atomize →
  select → check claims → re-source → sections.
- **Deterministic tail** (`python3 funnel/run.py <topic>`): pool → audit → enrich
  sources → scaffold config → **GATE** → render → telemetry. A failed input/output
  contract at any stage halts the chain with a readable error.

See [`PIPELINE.md`](PIPELINE.md) for the full architecture and the path contract,
and [`funnel/README.md`](funnel/README.md) for the deterministic core.

## Layout

| Path | What |
|---|---|
| `funnel/` | Deterministic gated core — orchestrator, contracts, the gate, pool build, audit, render glue |
| `engines.py` | Runs research engines (Gemini grounded, Perplexity sonar/deep, OpenAI deep research, Exa answer/research) |
| `atomize.js` | Splits an engine report into atomic claims |
| `check_claims.js` | Per-claim fact-check: honest source fetch (UA → r.jina.ai → Firecrawl) → bias-aware verdict |
| `resource.js` / `resolve_oa.py` | Re-source a valuable claim that lost its anchor; open-access full-text resolver |
| `deep-research-cheap.js` | Cost-split deep research (orchestration / search / fetch split across models) |
| `render_final.py`, `render_paged.py` | Swappable renderers (compact / paged consulting layout) |
| `docs/` | Methodology and render toolkit notes |
| `tests/` | Public-leak guard test |

## Running

```bash
python3 funnel/run.py <topic> ["Report title"]   # full gated tail
python3 funnel/test_funnel.py                      # gate tests
python3 funnel/gate.py <topic>                     # gate only (exit 1 = print refused)
```

Add a topic = create `facts.json` + `question.txt` under the topic directory;
the scripts create everything else. A minimal example lives in `topics/example/` —
run it as-is with no setup (see below).

## Data location — `RESEARCH_VAULT`

The engine is code only; your research data lives in a separate folder you point it
at with the `RESEARCH_VAULT` environment variable. One engine, each user's own data —
improving the engine improves everyone's runs, no fork.

- **No vault set** → the engine reads and writes `topics/` inside the repo. This is
  the bundled `topics/example/` demo, meant for a zero-setup trial and CI:

  ```bash
  python3 funnel/run.py example          # writes reports/REPORT-example-paged.html
  ```

- **Vault set** → `RESEARCH_VAULT` owns all reads and writes. Every topic lives under
  `$RESEARCH_VAULT/topics/<topic>/`, so a run can never touch the git-tracked
  `topics/example` fixture. Point it at any folder (a private git repo is recommended —
  the data is yours and never belongs in the public engine):

  ```bash
  export RESEARCH_VAULT=~/research-vault
  mkdir -p "$RESEARCH_VAULT/topics/<topic>"          # add facts.json + question.txt here
  python3 funnel/run.py <topic> "Report title"        # reads/writes under the vault
  ```

  A missing `RESEARCH_VAULT` directory is an error, not a silent fall-through to a repo
  write. Optional personalisation (a profile JSON) and the topic catalog also live in the
  vault; `funnel/publish.py` surfaces finished reports from the vault into your notes.

## Configuration

All API keys are read from the environment — **no secrets in the code**:
`GEMINI_API_KEY`, `PERPLEXITY_API_KEY`, `OPENAI_API_KEY`, `EXA_API_KEY`,
`ANTHROPIC_API_KEY`. Optional: `UNPAYWALL_EMAIL` (open-access resolver),
`RESEARCH_VAULT` (data root for every topic — see [Data location](#data-location--research_vault); default: repo `topics/` for the bundled example).

Requires Python 3.10+ and Node 18+ (for the `.js` tools).

> Note: the funnel handles sources in any language — a few internal matchers and
> regexes keep non-Latin character classes on purpose. The mechanism is language-agnostic.

## License

MIT — see [`LICENSE`](LICENSE).
