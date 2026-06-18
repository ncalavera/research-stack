#!/usr/bin/env python3
"""Free preflight BEFORE the long engine launch (engines.py).

Why: the engine stage makes long deep-research calls (each polls up to 10 min). If the input
is broken (no API key for a selected engine, empty question.txt, a typo in an engine name),
you want to learn that FOR FREE, before launch — not come back 10 minutes later to a pile of
JSON with a KeyError. Analogous to preflight.py, which guards check_claims.

Run:   python3 funnel/preflight_engines.py <topic> [eng1,eng2]
Exit:  0 — clean, engines.py can run;
       2 — problems found (printed), do NOT launch.

Reads only env and on-disk files — no network calls.
"""
import os
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "funnel"))
import paths as P
from engines import ENGINES, ENGINE_ENV

MIN_QUESTION_CHARS = 20  # empty/truncated question -> engines have nothing to search
ENGINE_RE = re.compile(r"^[a-z][a-z0-9_]{2,}$")


def preflight(topic: str, only=None) -> list:
    problems = []
    tdir = P.topic_dir(topic)
    if not tdir.exists():
        return [f"no topic dir: {tdir}"]

    # 1) question exists and is non-empty
    qf = P.question(topic)
    if not qf.exists():
        problems.append(f"no question.txt: {qf} — the skill must write the question first (stage 1)")
    else:
        q = qf.read_text("utf-8").strip()
        if len(q) < MIN_QUESTION_CHARS:
            problems.append(f"question.txt empty/truncated ({len(q)} chars, expected >= {MIN_QUESTION_CHARS})")

    # 2) selected engines exist (without this check a typo -> empty executor)
    engines = list(only) if only else list(ENGINES.keys())
    if not engines:
        return problems + ["engine list is empty — nothing to launch"]
    for eng in engines:
        if not ENGINE_RE.match(eng or "") or eng not in ENGINES:
            problems.append(f"engine «{eng}»: unknown. Available: {', '.join(ENGINES)}")

    # 3) each selected engine has its required env key
    #    (claude_deepresearch runs through Workflow — needs no env key, skipped)
    need = {}
    for eng in engines:
        env_var = ENGINE_ENV.get(eng)
        if env_var:
            need.setdefault(env_var, []).append(eng)
    for env_var, engs in sorted(need.items()):
        present = bool(os.environ.get(env_var))
        # exa supports an override key
        if env_var == "EXA_API_KEY" and os.environ.get("EXA_API_KEY_OVERRIDE"):
            present = True
        if not present:
            problems.append(f"missing env key {env_var} (needed by: {', '.join(engs)})")

    return problems


def main():
    if len(sys.argv) < 2:
        print("usage: python3 funnel/preflight_engines.py <topic> [eng1,eng2]", file=sys.stderr)
        sys.exit(64)
    topic = sys.argv[1]
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    problems = preflight(topic, only)
    if problems:
        print(f"[preflight_engines] topic {topic}: do NOT launch engines — {len(problems)} problems:")
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit(2)
    sel = ", ".join(only) if only else "all"
    print(f"[preflight_engines] topic {topic}: clean ✓ — question present, engines ({sel}) known, keys present.")
    sys.exit(0)


if __name__ == "__main__":
    main()
