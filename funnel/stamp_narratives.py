#!/usr/bin/env python3
"""stamp_narratives — "signature" of the prose on the current pool.

Writes topics/<topic>/narratives.lock = {pool_hash, nfacts} for the current pool.json.
Run AFTER narratives.json has been written/updated for the current set of facts.
sync_gate checks this fingerprint: if the pool changes after — printing
is blocked until the prose is rewritten and re-stamped.

Usage: python3 funnel/stamp_narratives.py <topic>
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
    pool_path = P.pool(topic)
    d = json.load(open(pool_path))
    facts = d if isinstance(d, list) else d.get("facts", [])
    fids = [f["fid"] for f in facts]
    h = hashlib.sha1("\n".join(sorted(fids)).encode()).hexdigest()[:16]
    lock_path = P.narratives_lock(topic)
    json.dump({"pool_hash": h, "nfacts": len(fids)},
              open(lock_path, "w"), ensure_ascii=False, indent=2)
    print(f"✓ prose stamped on pool: {len(fids)} facts, fingerprint {h} → narratives.lock")


if __name__ == "__main__":
    main()
