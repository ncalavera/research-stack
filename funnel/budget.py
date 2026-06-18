#!/usr/bin/env python3
"""Spend ceiling for a topic run — over EXACT engine API costs only.

Why: the engine stage hits paid third-party APIs (Perplexity, OpenAI, Exa, Gemini), and a
runaway or accidental over-wide engine set can burn real money. Each engine returns its exact
cost in cost_est; this sums those and compares them to a ceiling, so an oversized run is caught
before the next paid stage.

NOT counted: the atomize / check_claims agent fan-out. Those run on the Claude Max subscription,
not per-token API billing, so there is no exact marginal price to sum — guessing it would be
misleading, so it is deliberately excluded.

Ceiling source (first wins): --ceiling <usd>  ·  env RESEARCH_BUDGET_USD  ·  default 5.0.

Run:   python3 funnel/budget.py <topic> [--ceiling <usd>]
Exit:  0 — within ceiling;  2 — ceiling exceeded (do not start the next paid engine run).
"""
import json
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

DEFAULT_CEILING = 5.0


def engine_spend(topic) -> tuple:
    """(total, {engine: cost}) of exact cost_est across engines/*.json (null/missing -> 0)."""
    edir = P.engines_dir(topic)
    by_engine = {}
    if not edir.exists():
        return 0.0, by_engine
    for f in sorted(edir.glob("*.json")):
        try:
            d = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        c = d.get("cost_est")
        by_engine[f.stem] = round(c, 4) if isinstance(c, (int, float)) else 0.0
    return round(sum(by_engine.values()), 4), by_engine


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("usage: python3 funnel/budget.py <topic> [--ceiling <usd>]", file=sys.stderr)
        sys.exit(64)
    topic = args[0]

    ceiling = float(os.environ.get("RESEARCH_BUDGET_USD", DEFAULT_CEILING))
    argv = sys.argv[1:]
    if "--ceiling" in argv:
        ceiling = float(argv[argv.index("--ceiling") + 1])

    spent, by_engine = engine_spend(topic)
    detail = ", ".join(f"{e} ${c}" for e, c in by_engine.items()) or "—"
    print(f"[budget] {topic}: engine API spend ${spent} / ceiling ${ceiling}  ({detail})")
    print("  (atomize/check_claims agents excluded — Claude Max subscription, no per-token price)")

    if spent > ceiling:
        over = round(spent - ceiling, 4)
        print(f"✗ ceiling exceeded by ${over} — do NOT start another paid engine run. "
              f"Raise it (--ceiling / RESEARCH_BUDGET_USD) only deliberately.", file=sys.stderr)
        sys.exit(2)
    print(f"✓ within ceiling (${round(ceiling - spent, 4)} left).")
    sys.exit(0)


if __name__ == "__main__":
    main()
