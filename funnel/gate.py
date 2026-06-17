#!/usr/bin/env python3
"""Hard guard before printing the report.

Walks all pool facts and kills the build if even one fact lacks a live backing
(SUPPORTED/PARTIAL + non-empty link), is marked as fabricated, or is missing best_source.
This is what "formally cannot be bypassed" means: report printing stands AFTER this gate,
so an unconfirmed fact physically cannot reach the output.

Usage: python3 funnel/gate.py <topic>   (exit 1 = blocked, printing not allowed)
"""
import sys
from contracts import guard_report_safe, untraceable_in_pool, validate_pool, StageError

topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
try:
    n = validate_pool(topic)
    bad = guard_report_safe(topic)          # HARD: dead/fake/fabricated backing
    orphan = untraceable_in_pool(topic)     # SOFT: source not from verdicts/re-sourcing
except StageError as e:
    print(f"✗ guard: {e}")
    sys.exit(2)

# Soft warning: traceability. Does not block — Opus clarification and re-sourcing
# legitimately bring new sources. This is a "check manually" signal, not a ban.
if orphan:
    print(f"⚠ traceability: {len(orphan)} of {n} facts with a source outside verdicts/re-sourcing:")
    for o in orphan[:10]:
        print(f"    #{o['i']}: «{o['text']}…»")
    if len(orphan) > 10:
        print(f"    … and {len(orphan) - 10} more. Verify these are curated, not bypassed injections.")

# Hard gate: no dead/fake/fabricated backing allowed.
if bad:
    print(f"✗ GUARD BLOCKED printing: {len(bad)} of {n} facts without live backing:")
    for b in bad[:20]:
        print(f"  #{b['i']}: {b['reason']} — «{b['text']}…»")
    if len(bad) > 20:
        print(f"  … and {len(bad) - 20} more")
    print("Restore the fact's live backing (re-sourcing) or remove it from the pool. Printing blocked.")
    sys.exit(1)

print(f"✓ guard: all {n} facts have live backing — printing allowed" +
      (f" ({len(orphan)} for manual review)" if orphan else ""))
