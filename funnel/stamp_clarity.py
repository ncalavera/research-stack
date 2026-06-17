#!/usr/bin/env python3
"""stamp_clarity — "signature" of the clarity audit on the current prose.

Writes topics/<topic>/clarity.lock = {narratives_hash} for the current narratives.json.
Run AFTER the Opus clarity editor pass (step 8.5). sync_gate compares this
fingerprint with the current narratives.json: if the prose was edited without a new audit —
printing is blocked. This way the clarity audit cannot be silently skipped (root of bad
text on 14.06.2026).

Usage: python3 funnel/stamp_clarity.py <topic>
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def narratives_hash(topic):
    p = os.path.join(ROOT, "topics", topic, "narratives.json")
    return hashlib.sha1(open(p, "rb").read()).hexdigest()[:16]


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
    h = narratives_hash(topic)
    lock = os.path.join(ROOT, "topics", topic, "clarity.lock")
    json.dump({"narratives_hash": h}, open(lock, "w"), ensure_ascii=False, indent=2)
    print(f"✓ clarity audit stamped on prose: fingerprint {h} → clarity.lock")


if __name__ == "__main__":
    main()
