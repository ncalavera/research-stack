#!/usr/bin/env python3
"""Parallel pre-fetch of sources for check-claims.

Accepts a list of URLs (from a claims JSON file or explicitly via --urls),
deduplicates them, calls ./fetch_url.sh for each unique URL
(up to 6 workers), saves page text to runs/_fetched/<sha1>.txt,
builds an index {url: {file, alive, via, bytes}} — to stdout AND to a file
runs/_fetched/index_<sha1-of-input>.json.

Dead/unauditable URLs: alive=false, file=null (no file is created;
fetch already failed inside fetch_url.sh).

Usage:
  python3 prefetch.py --claims runs/topic1/perplexity_sonar.json
  python3 prefetch.py --urls https://example.com https://gov.uk/page
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Repository root — always adjacent to this script (not cwd, not a worktree).
ROOT = pathlib.Path(__file__).parent.resolve()
FETCH_SCRIPT = ROOT / "fetch_url.sh"
FETCHED_DIR = ROOT / "runs" / "_fetched"

# Maximum concurrent fetch_url.sh calls (Firecrawl has a rate limit;
# more than 6 gives no throughput gain and burns quota).
MAX_WORKERS = 6

# Timeout for a single fetch (seconds). fetch_url.sh already limits curl,
# but subprocess also guards against a hung bash process.
FETCH_TIMEOUT_SEC = 150


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def extract_urls_from_claims(claims_path: pathlib.Path) -> list[str]:
    """Extract all non-empty source URLs from a claims JSON (field claims[].source)."""
    d = json.loads(claims_path.read_text())
    claims = d.get("claims", [])
    urls = [c["source"] for c in claims if c.get("source")]
    return urls


def fetch_one(url: str) -> dict:
    """Call fetch_url.sh for one URL, return {url, file, alive, via, bytes}."""
    key = sha1(url)
    out_file = FETCHED_DIR / f"{key}.txt"

    # If fetch_url.sh already has the result cached, the page was fetched before.
    # fetch_url.sh prints the cache on repeated calls (exit 0), so
    # just run the script — it returns the cache quickly without network requests.
    try:
        result = subprocess.run(
            ["bash", str(FETCH_SCRIPT), url],
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return {"url": url, "file": None, "alive": False, "via": "timeout", "bytes": 0}
    except Exception as e:
        return {"url": url, "file": None, "alive": False, "via": f"err:{e}", "bytes": 0}

    stdout = result.stdout

    # fetch_url.sh signals status via the last line (__SOURCE__ / __DEAD__ / __UNAUDITABLE__).
    lines = stdout.splitlines()
    last = lines[-1].strip() if lines else ""

    if result.returncode == 0 and last.startswith("__SOURCE__"):
        # Success: everything above the last line is the page text.
        page_text = "\n".join(lines[:-1])
        # Determine via from the marker: "__SOURCE__ direct http=200 len=12345" → "direct".
        parts = last.split()
        via = parts[1] if len(parts) > 1 else "direct"

        # Write page text to runs/_fetched/<sha1>.txt.
        FETCHED_DIR.mkdir(parents=True, exist_ok=True)
        out_file.write_text(page_text, encoding="utf-8")
        return {
            "url": url,
            "file": str(out_file),
            "alive": True,
            "via": via,
            "bytes": len(page_text.encode("utf-8")),
        }
    else:
        # Dead/unauditable URL: no file is created, alive=false.
        via = "dead"
        if "__UNAUDITABLE__" in stdout:
            via = "unauditable"
        elif "timeout" in stdout.lower():
            via = "timeout"
        return {"url": url, "file": None, "alive": False, "via": via, "bytes": 0}


def build_index(entries: list[dict]) -> dict:
    """Build an index {url: {file, alive, via, bytes}} from a list of fetch results."""
    return {
        e["url"]: {
            "file": e["file"],
            "alive": e["alive"],
            "via": e["via"],
            "bytes": e["bytes"],
        }
        for e in entries
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parallel pre-fetch of sources for check-claims."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--claims",
        metavar="PATH",
        help="Path to a claims JSON file (field claims[].source). "
        "URL deduplication is automatic.",
    )
    group.add_argument(
        "--urls",
        nargs="+",
        metavar="URL",
        help="List of URLs to pre-fetch (passed explicitly).",
    )
    args = parser.parse_args()

    # Build the list of unique URLs (insertion order preserved via dict).
    if args.claims:
        claims_path = pathlib.Path(args.claims).resolve()
        if not claims_path.exists():
            sys.exit(f"File not found: {claims_path}")
        raw_urls = extract_urls_from_claims(claims_path)
        input_sig = sha1(str(claims_path))
    else:
        raw_urls = args.urls
        input_sig = sha1(" ".join(raw_urls))

    # Deduplicate, preserving first-occurrence order.
    seen: dict[str, bool] = {}
    urls = [u for u in raw_urls if u and not seen.__setitem__(u, True) and u not in seen or u in seen]
    # Simpler rewrite — standard dict dedup:
    urls = list(dict.fromkeys(u for u in raw_urls if u))

    if not urls:
        sys.exit("No URLs to fetch.")

    print(f"[prefetch] total unique URLs: {len(urls)}", file=sys.stderr)

    # Parallel fetch (up to MAX_WORKERS at a time).
    entries: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_one, url): url for url in urls}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                entry = fut.result()
            except Exception as e:
                entry = {"url": url, "file": None, "alive": False, "via": f"err:{e}", "bytes": 0}
            entries.append(entry)
            status = "✓" if entry["alive"] else "✗"
            print(
                f"[prefetch] {status} {entry['via']:20} {url[:80]}",
                file=sys.stderr,
            )

    index = build_index(entries)

    # Save index to runs/_fetched/index_<sig>.json.
    FETCHED_DIR.mkdir(parents=True, exist_ok=True)
    index_path = FETCHED_DIR / f"index_{input_sig}.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"[prefetch] index → {index_path}", file=sys.stderr)

    # Structured output to stdout for the calling agent.
    out = {
        "entries": [
            {
                "url": url,
                "file": index[url]["file"],
                "alive": index[url]["alive"],
                "via": index[url]["via"],
            }
            for url in urls
            if url in index
        ],
        "index_path": str(index_path),
        "urls_total": len(urls),
        "urls_alive": sum(1 for e in index.values() if e["alive"]),
        "urls_dead": sum(1 for e in index.values() if not e["alive"]),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
