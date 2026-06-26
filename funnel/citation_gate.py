#!/usr/bin/env python3
"""citation_gate — hard gate: "every link in the prose points at a verified source".

Root cause of broken links: an editor shortens a URL by hand (a truncated path
instead of the full one) or points a link at a source that is not in the pool.
Such an href leads to a 404 or to the wrong material — "links break".

Rule: every `href` in narratives.json MUST match VERBATIM the URL of some
verified pool fact (`best_source` or any provenance source). No match → the gate
fails (exit 1) and reports the break.

Run: python3 funnel/citation_gate.py <topic>
"""
import json
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P


def pool_urls(topic: str) -> set:
    pool = json.loads(P.pool(topic).read_text("utf-8"))
    facts = pool if isinstance(pool, list) else pool.get("facts", [])
    urls = set()
    for f in facts:
        if f.get("best_source"):
            urls.add(f["best_source"].strip())
        for pr in f.get("provenance", []):
            u = pr.get("source") or pr.get("final_source")
            if u:
                urls.add(u.strip())
    return urls


def prose_hrefs(topic: str):
    cfg_path = P.config(topic)
    narr_file = P.narratives(topic)
    if cfg_path.exists():
        nf = json.loads(cfg_path.read_text("utf-8")).get("narratives_file")
        if nf:
            # Resolve the config-supplied name inside the (vault-aware) topic
            # dir by basename, so it never escapes to the repo root.
            narr_file = P.topic_dir(topic) / pathlib.Path(nf).name
    text = pathlib.Path(narr_file).read_text("utf-8")
    return re.findall(r"href=['\"]([^'\"]+)['\"]", text)


def check(topic: str) -> list:
    ok = pool_urls(topic)
    problems = []
    for h in prose_hrefs(topic):
        if h.strip() not in ok:
            near = [u for u in ok if u.startswith(h[:45]) or h.startswith(u[:45])]
            hint = f" (looks like: {near[0]})" if near else " (source not in pool)"
            problems.append((h, hint))
    return problems


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
    problems = check(topic)
    if not problems:
        print("✓ citation gate: every prose href points at a verified pool source")
        return 0
    print(f"✗ citation gate: {len(problems)} href(s) outside the pool (broken/truncated/foreign source):")
    for h, hint in problems:
        print(f"  • {h}{hint}")
    print("  Copy each link VERBATIM from the fact's best_source; do not truncate the URL.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
