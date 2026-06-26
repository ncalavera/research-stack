#!/usr/bin/env python3
"""scope_gate — soft gate: "personal context did not leak into the report".

Root cause of a leak: an owner's personal goal (a visa application, a media pack,
a health matter) gets written into the research question, and the funnel honestly
researches it — the personal leaked into a report meant for someone else.

The gate scans the INPUTS (question.txt, facts.json) and the OUTPUT
(narratives.json) for personal-context markers. It fires softly (warning + exit 0
by default): printing is not blocked, but the trace is visible. Hard mode — flag
--hard (exit 1), to wire it into the pipeline as a blocker for published reports.

Run: python3 funnel/scope_gate.py <topic> [--hard]
Whitelist a marker that is genuinely on-topic for this report in
topics/<topic>/scope_allow.json = {"allow": ["marker-string", …]}.
"""
import json
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

# Markers of personal / off-profile context. Case-insensitive.
PERSONAL = [
    r"global talent", r"talent visa", r"\bвиз[аыуе]\b", r"\bvisa\b", r"медиапак",
    r"media pack", r"релокац", r"вид на жительство", r"\bВНЖ\b", r"гражданств",
    r"\bтерапи", r"\bhealth\b", r"\bздоровь", r"паспорт", r"иммиграц",
]
_RE = re.compile("|".join(PERSONAL), re.IGNORECASE)


def _read(path) -> str:
    p = pathlib.Path(path)
    return p.read_text("utf-8") if p.exists() else ""


def check(topic: str) -> list:
    allow = set()
    ap = P.topic_dir(topic) / "scope_allow.json"
    if ap.exists():
        allow = {a.lower() for a in json.loads(ap.read_text("utf-8")).get("allow", [])}
    hits = []
    for path in (P.question(topic), P.facts(topic), P.narratives(topic)):
        text = _read(path)
        for m in _RE.finditer(text):
            frag = text[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")
            if any(a in frag.lower() for a in allow):
                continue
            hits.append((pathlib.Path(path).name, m.group(0), frag))
    return hits


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    hard = "--hard" in sys.argv
    topic = args[0] if args else "topic1"
    hits = check(topic)
    if not hits:
        print("✓ scope gate: no personal markers (visa/media pack/health…) found")
        return 0
    print(f"{'✗' if hard else '⚠'} scope gate: {len(hits)} personal-context marker(s):")
    seen = set()
    for name, term, frag in hits:
        k = (name, term)
        if k in seen:
            continue
        seen.add(k)
        print(f"  • [{name}] «{term}» — …{frag}…")
    print("  Personal context does not belong in a report for someone else. Remove it from the")
    print("  inputs (question/facts) and the prose, or confirm as on-topic in topics/<topic>/scope_allow.json.")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
