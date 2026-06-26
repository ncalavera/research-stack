#!/usr/bin/env python3
"""Public-leak guard.

Scans the repository for any forbidden token from ``tests/denylist.txt`` and
fails on the first match. This is the permanent gate that replaces eyeball
review: once green, no owner identity, infra path, internal ticket id, or
private research topic remains in the published tree.

Run standalone::

    python3 tests/test_no_public_leaks.py

or under pytest::

    pytest tests/test_no_public_leaks.py
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DENYLIST = pathlib.Path(__file__).resolve().parent / "denylist.txt"
DENYLIST_PRIVATE = pathlib.Path(__file__).resolve().parent / "denylist.private.txt"

# Directories never scanned. `docs/` holds planning prose (brainstorms, plans)
# that legitimately names the very tokens being scrubbed from shipped code; the
# guard protects code and data, not the planning record.
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".fetch_cache", ".bakeoff", "docs"}
# Files never scanned (the denylists and this test legitimately contain the tokens).
SKIP_FILES = {
    DENYLIST.resolve(),
    DENYLIST_PRIVATE.resolve(),
    pathlib.Path(__file__).resolve(),
}
# Only scan text-ish files.
TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".sh", ".md", ".json", ".jsonl", ".txt",
    ".yaml", ".yml", ".toml", ".cfg", ".ini", ".html", ".css",
}


def _load_patterns():
    pats = []
    for denyfile in [DENYLIST, DENYLIST_PRIVATE]:
        if not denyfile.exists():
            continue
        for line in denyfile.read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pats.append(re.compile(line, re.IGNORECASE))
    return pats


def _iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def find_leaks():
    patterns = _load_patterns()
    hits = []
    for path in _iter_files():
        try:
            text = path.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in patterns:
                if pat.search(line):
                    rel = path.relative_to(ROOT)
                    hits.append((str(rel), lineno, pat.pattern, line.strip()[:120]))
    return hits


def test_no_public_leaks():
    hits = find_leaks()
    assert not hits, "Forbidden tokens found:\n" + "\n".join(
        f"  {f}:{n}  /{p}/  {snippet}" for f, n, p, snippet in hits
    )


def _stray_topics():
    """Tracked topic paths outside topics/example/ — real research must never ship."""
    import subprocess
    out = subprocess.run(
        ["git", "ls-files", "topics/"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.splitlines()
    return [p for p in out if p.strip() and not p.startswith("topics/example/")]


def test_only_example_topic_is_tracked():
    stray = _stray_topics()
    assert not stray, (
        "Topics other than the bundled example are tracked — real research data "
        "must stay in the vault:\n  " + "\n  ".join(stray)
    )


if __name__ == "__main__":
    leaks = find_leaks()
    stray = _stray_topics()
    if leaks or stray:
        if leaks:
            print(f"LEAK: {len(leaks)} forbidden token(s) found:")
            for f, n, p, snippet in leaks:
                print(f"  {f}:{n}  /{p}/  {snippet}")
        if stray:
            print(f"LEAK: {len(stray)} non-example topic path(s) tracked:")
            for p in stray:
                print(f"  {p}")
        raise SystemExit(1)
    print("OK — no public leaks.")
