#!/usr/bin/env python3
"""sync_gate — two hard gates against "step sort of done":

  #1 PROSE FRESHNESS. Prose (narratives.json) must be written for the CURRENT pool.
     The fingerprint of the fact set (sorted fid → sha1) is fixed by the stamp
     stamp_narratives.py in `topics/<topic>/narratives.lock`. If the pool has since
     changed (additional facts, rebuild) — the gate kills the build: "pool grew from N to
     M, rewrite prose and re-stamp". Catches case 14.06.2026: pool grew from 27 to
     85 facts but prose stayed at 27.

  #2 SECTION COMPLETENESS. Every pool fact must be in sections.json under a real
     chapter from config.section_order. Any unsectioned fact (will fall into
     "Other" as raw dump) — block. Catches case: 59 of 85 facts without a chapter.

Usage: python3 funnel/sync_gate.py <topic>   (exit 1 = block, printing not allowed)
Override stamp consciously: --accept-stale (printing on old prose under your responsibility).
"""
import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P


def _p(topic, *parts):
    return os.path.join(P.topic_dir(topic), *parts)


def load_pool_fids(topic):
    d = json.load(open(_p(topic, "pool.json")))
    facts = d if isinstance(d, list) else d.get("facts", [])
    return [f["fid"] for f in facts], facts


def pool_hash(fids):
    return hashlib.sha1("\n".join(sorted(fids)).encode()).hexdigest()[:16]


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
    accept_stale = "--accept-stale" in sys.argv

    fids, facts = load_pool_fids(topic)
    nfacts = len(fids)
    errors = []

    # ── Gate #2: section completeness ─────────────────────────────────
    sec_path = _p(topic, "sections.json")
    sections = json.load(open(sec_path)) if os.path.exists(sec_path) else {}
    # allowed chapters — from config.section_order (if config exists)
    cfg_path = _p(topic, "config.json")
    allowed = None
    if os.path.exists(cfg_path):
        allowed = set(json.load(open(cfg_path)).get("section_order", [])) or None

    unsectioned = [f["fid"] for f in facts if f["fid"] not in sections]
    if unsectioned:
        errors.append(
            f"SECTIONS: {len(unsectioned)} of {nfacts} facts without a chapter "
            f"(will fall into 'Other'): {', '.join(unsectioned[:8])}"
            + (" …" if len(unsectioned) > 8 else "")
        )
    if allowed:
        stray = sorted({sections[f["fid"]] for f in facts
                        if f["fid"] in sections and sections[f["fid"]] not in allowed})
        if stray:
            errors.append(
                f"SECTIONS: chapters outside config.section_order: {', '.join(stray)} "
                f"— add to section_order or reassign facts"
            )

    # ── Gate #1: prose freshness ──────────────────────────────────────
    cur = pool_hash(fids)
    lock_path = _p(topic, "narratives.lock")
    nar_path = _p(topic, "narratives.json")
    if not os.path.exists(nar_path):
        errors.append("PROSE: narratives.json missing — write layout (step 8) before printing")
    elif not os.path.exists(lock_path):
        errors.append(
            f"PROSE: no stamp narratives.lock — prose not signed against the pool "
            f"({nfacts} facts). Review the text and run: "
            f"python3 funnel/stamp_narratives.py {topic}"
        )
    else:
        lock = json.load(open(lock_path))
        if lock.get("pool_hash") != cur:
            errors.append(
                f"PROSE STALE: pool changed since prose was written "
                f"(was {lock.get('nfacts', '?')} facts → now {nfacts}). "
                f"Rewrite/supplement narratives.json for the new facts and re-stamp: "
                f"python3 funnel/stamp_narratives.py {topic}"
            )

    # ── Gate #3: clarity audit passed on CURRENT prose ─────────────────
    # clarity.lock stores the fingerprint of narratives.json that the
    # Opus clarity editor signed off on (step 8.5). If prose was changed after — fingerprint diverges.
    if os.path.exists(nar_path):
        clarity_path = _p(topic, "clarity.lock")
        nar_hash = hashlib.sha1(open(nar_path, "rb").read()).hexdigest()[:16]
        if not os.path.exists(clarity_path):
            errors.append(
                "CLARITY: clarity audit not run (no clarity.lock). Run "
                f"the Opus clarity editor per CLARITY STANDARD, then: "
                f"python3 funnel/stamp_clarity.py {topic}"
            )
        elif json.load(open(clarity_path)).get("narratives_hash") != nar_hash:
            errors.append(
                "CLARITY STALE: prose was edited after the clarity audit. Run "
                f"the Opus editor again and re-stamp: python3 funnel/stamp_clarity.py {topic}"
            )

    if errors:
        _waivable = ("PROSE STALE", "CLARITY")
        if accept_stale and all(e.startswith(_waivable) for e in errors):
            print("⚠ sync_gate: prose/clarity stale, but printing allowed by --accept-stale flag")
            return
        print(f"✗ SYNC GATE BLOCKED printing ({len(errors)}):")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)

    print(f"✓ sync gate: prose fresh (stamp {cur}), all {nfacts} facts in chapters")


if __name__ == "__main__":
    main()
