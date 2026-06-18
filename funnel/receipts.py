#!/usr/bin/env python3
"""Append-only per-stage receipts in topics/<topic>/manifest.json.

Why: re-runs can silently change artifacts (a fresh timeout overwriting yesterday's good
output, a pool rebuilt from different verdicts). A receipt records, for a stage, the git sha
and a content hash of each input/output file, so drift between runs is visible after the fact.
Append-only: a receipt is never edited or removed, only added.

Stored under manifest.json -> "receipts": [ {stage, ts, git_sha, inputs:{rel:hash}, outputs:{rel:hash}} ].
Lives alongside the existing "rounds" list (archive_evidence.py) — same file, separate key.

Use as a library:
    import receipts; receipts.stamp(topic, "render", inputs=[...paths], outputs=[...paths])
Or from the CLI:
    python3 funnel/receipts.py <topic> <stage> --in a.json b.json --out c.html
"""
import datetime
import hashlib
import json
import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

ROOT = P.ROOT


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def _hash(path: pathlib.Path) -> str:
    """Short content hash of a file (sha1, first 12 hex). 'missing' if absent."""
    if not path.exists():
        return "missing"
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _rel(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def stamp(topic: str, stage: str, inputs=None, outputs=None) -> dict:
    """Append one receipt for a stage. inputs/outputs — iterables of pathlib.Path. Returns it."""
    def _digest(paths):
        return {_rel(pathlib.Path(p)): _hash(pathlib.Path(p)) for p in (paths or [])}

    entry = {
        "stage": stage,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "inputs": _digest(inputs),
        "outputs": _digest(outputs),
    }
    mpath = P.manifest(topic)
    data = {}
    if mpath.exists():
        try:
            data = json.loads(mpath.read_text("utf-8"))
        except Exception:
            data = {}
    data.setdefault("receipts", []).append(entry)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def main():
    argv = sys.argv[1:]
    pos = [a for a in argv if not a.startswith("-")]
    if len(pos) < 2:
        print("usage: python3 funnel/receipts.py <topic> <stage> [--in f1 f2] [--out f1 f2]",
              file=sys.stderr)
        sys.exit(64)
    topic, stage = pos[0], pos[1]

    def _collect(flag):
        if flag not in argv:
            return []
        out, i = [], argv.index(flag) + 1
        while i < len(argv) and not argv[i].startswith("-"):
            out.append(argv[i])
            i += 1
        return out

    entry = stamp(topic, stage, inputs=_collect("--in"), outputs=_collect("--out"))
    print(f"[receipts] {topic}: stamped '{stage}' @ {entry['git_sha']} "
          f"({len(entry['inputs'])} in, {len(entry['outputs'])} out)")


if __name__ == "__main__":
    main()
