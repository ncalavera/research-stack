#!/usr/bin/env python3
"""Archives source pages for one run.

Collects all URLs from topic verdicts (fields source and final_source),
looks for cached text, copies it to topics/<topic>/evidence/
in compressed form (.txt.gz). Updates the index evidence/index.json.

Usage:
    python3 funnel/archive_evidence.py <topic>
    python3 funnel/archive_evidence.py <topic> --manifest --mode light|deep

Options:
    --manifest          add a round entry to topics/<topic>/manifest.json
    --mode light|deep   run mode (used together with --manifest)
"""
import argparse
import gzip
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
from datetime import datetime

# Repository root — script lives in funnel/, its sibling by level
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P


def _sha1(url: str) -> str:
    """Returns the SHA-1 hex digest of the URL."""
    return hashlib.sha1(url.encode()).hexdigest()


def _collect_urls(topic: str) -> set[str]:
    """Collects unique URLs from all topic verdicts (fields source and final_source)."""
    vdir = P.verdicts_dir(topic)
    urls: set[str] = set()
    if not vdir.exists():
        return urls
    for f in sorted(vdir.glob("*.json")):
        try:
            data = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        for claim in data.get("claims", []):
            for field in ("source", "final_source"):
                val = (claim.get(field) or "").strip()
                if val.startswith("http"):
                    urls.add(val)
    return urls


def _find_cached_text(sha: str) -> bytes | None:
    """Looks for cached page text by SHA-1.

    Search order:
    1. .fetch_cache/<sha>          — primary cache (plain text, no extension)
    2. runs/_fetched/<sha>.txt     — secondary cache (plain text, .txt)
    Returns bytes or None if not found in either cache.
    """
    p1 = ROOT / ".fetch_cache" / sha
    if p1.exists():
        return p1.read_bytes()
    p2 = ROOT / "runs" / "_fetched" / (sha + ".txt")
    if p2.exists():
        return p2.read_bytes()
    return None


def _read_index(index_path: pathlib.Path) -> dict:
    """Reads existing index.json or returns an empty dict."""
    if index_path.exists():
        try:
            return json.loads(index_path.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _write_index(index_path: pathlib.Path, index: dict) -> None:
    """Writes index.json with indentation."""
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def archive(topic: str) -> tuple[int, int, int]:
    """Archives topic sources.

    Returns a tuple (archived, already, missing).
    """
    urls = _collect_urls(topic)
    if not urls:
        print(f"[archive_evidence] {topic}: no verdicts found or URLs absent")
        return 0, 0, 0

    evidence_dir = P.evidence_dir(topic)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    index_path = evidence_dir / "index.json"
    index = _read_index(index_path)

    archived = already = missing = 0
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")

    for url in sorted(urls):
        sha = _sha1(url)
        gz_name = sha + ".txt.gz"
        gz_path = evidence_dir / gz_name

        # Skip if already archived
        if gz_path.exists():
            already += 1
            # Make sure index entry exists
            if url not in index:
                index[url] = {
                    "file": gz_name,
                    "sha1": sha,
                    "bytes_raw": None,
                    "archived_at": now_iso,
                }
            continue

        raw = _find_cached_text(sha)
        if raw is None:
            missing += 1
            index[url] = {"file": None, "note": "not in cache"}
            continue

        # Compress and save
        with gzip.open(gz_path, "wb") as fh:
            fh.write(raw)

        index[url] = {
            "file": gz_name,
            "sha1": sha,
            "bytes_raw": len(raw),
            "archived_at": now_iso,
        }
        archived += 1

    _write_index(index_path, index)
    return archived, already, missing


def _engines_from_verdicts(topic: str) -> list[str]:
    """Determines the list of engines from verdict filenames (without -core suffix)."""
    vdir = P.verdicts_dir(topic)
    engines = []
    if not vdir.exists():
        return engines
    for f in sorted(vdir.glob("*.json")):
        if not f.stem.endswith("-core"):
            engines.append(f.stem)
    return engines


def _git_sha() -> str:
    """Returns the short HEAD SHA or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _append_manifest(topic: str, mode: str) -> None:
    """Adds a round entry to topics/<topic>/manifest.json."""
    manifest_path = P.manifest(topic)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text("utf-8"))
        except Exception:
            data = {"rounds": []}
    else:
        data = {"rounds": []}

    question_file = f"topics/{topic}/question.txt"

    entry = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "engines": _engines_from_verdicts(topic),
        "question_file": question_file,
        "git_sha": _git_sha(),
    }
    data.setdefault("rounds", []).append(entry)
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[archive_evidence] manifest updated: topics/{topic}/manifest.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archives source pages from topic verdicts"
    )
    parser.add_argument("topic", help="topic slug (e.g. topic1, example-topic)")
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="add a round entry to runs/<topic>/manifest.json",
    )
    parser.add_argument(
        "--mode",
        choices=["light", "deep", "unknown"],
        default="unknown",
        help="run mode (light|deep|unknown), used with --manifest",
    )
    args = parser.parse_args()

    archived, already, missing = archive(args.topic)
    total = archived + already + missing
    print(
        f"[archive_evidence] {args.topic}: "
        f"archived {archived} / already had {already} / not in cache {missing} "
        f"(total URLs {total})"
    )

    if args.manifest:
        _append_manifest(args.topic, args.mode)


if __name__ == "__main__":
    main()
