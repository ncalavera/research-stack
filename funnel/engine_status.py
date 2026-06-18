#!/usr/bin/env python3
"""Engine-stage contract: classify each engines/<engine>.json and count coverage.

Why: a dead engine (timeout, non-completed status, empty report) used to sit silently on
disk and quietly drop coverage — the report would still "assemble", but from 2 sources
instead of 5. This module gives each engine an honest status and an "N/M ok" summary, which
the post-check (engines.py) and the auditor (doctor.py) build on.

Statuses:
    ok      — has a usable report (>= MIN_REPORT_CHARS), directly or after normalization
    legacy  — old claude_deepresearch schema (summary/findings without report); normalized
              with the same logic as save_claude_dr.py. If the normalized text is usable it
              counts as coverage (usable=True), but the status stays 'legacy' to flag migration.
    error   — engine returned {"error": ...} (timeout, non-completed status, exception)
    empty   — file exists, but the report is empty/truncated and not legacy
    missing — no file

Coverage (usable) is granted by ok and legacy. error/empty/missing — no.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

MIN_REPORT_CHARS = 200


def normalize_claude(d: dict) -> str:
    """Old claude_deepresearch summary/findings/caveats -> flat report.

    Same assembly as save_claude_dr.py (small logic intentionally duplicated here to avoid
    pulling in the save script's side effects)."""
    r = d.get("result", d)
    parts = [(r.get("summary") or "").strip(), ""]
    for f in r.get("findings", []) or []:
        parts.append((f.get("claim") or "").strip())
        if f.get("evidence"):
            parts.append("  Evidence: " + f["evidence"].strip())
        parts.append(f"  [confidence: {f.get('confidence','')}, votes: {f.get('vote','')}]")
        parts.append("")
    caveats = r.get("caveats", [])
    if isinstance(caveats, str):
        caveats = [caveats]
    for c in caveats or []:
        parts.append("Caveat: " + (c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)))
    return "\n".join(parts).strip()


def _is_legacy_claude(d: dict) -> bool:
    """Old schema: no string report, but has findings/summary."""
    if isinstance(d.get("report"), str):
        return False
    r = d.get("result", d)
    return bool(r.get("findings") or r.get("summary"))


def classify(d: dict) -> dict:
    """Classify one parsed engine JSON. Returns {status, usable, chars, detail}."""
    if not isinstance(d, dict):
        return {"status": "empty", "usable": False, "chars": 0, "detail": "not an object"}
    if d.get("error"):
        return {"status": "error", "usable": False, "chars": 0, "detail": str(d["error"])[:120]}
    report = d.get("report")
    if isinstance(report, str) and len(report) >= MIN_REPORT_CHARS:
        return {"status": "ok", "usable": True, "chars": len(report), "detail": ""}
    if _is_legacy_claude(d):
        norm = normalize_claude(d)
        usable = len(norm) >= MIN_REPORT_CHARS
        return {"status": "legacy", "usable": usable, "chars": len(norm),
                "detail": "summary/findings schema — normalized" if usable else "legacy but empty"}
    chars = len(report) if isinstance(report, str) else 0
    return {"status": "empty", "usable": False, "chars": chars,
            "detail": f"report {chars} chars (< {MIN_REPORT_CHARS})"}


def status_for_file(path: pathlib.Path) -> str:
    """Short status from a path to engines/<engine>.json (missing if absent)."""
    if not path.exists():
        return "missing"
    try:
        d = json.loads(path.read_text("utf-8"))
    except Exception:
        return "empty"
    return classify(d)["status"]


def audit_topic(topic: str, only=None) -> dict:
    """Per-topic summary: {engine: {status, usable, chars, detail}} for the selected engines.

    only — list of engine names (run intent). None -> all files in engines/.
    A missing selected engine -> status=missing (important for the post-check)."""
    edir = P.engines_dir(topic)
    if only:
        names = list(only)
    else:
        names = sorted(p.stem for p in edir.glob("*.json")) if edir.exists() else []
    out = {}
    for name in names:
        path = P.engine_raw(topic, name)
        if not path.exists():
            out[name] = {"status": "missing", "usable": False, "chars": 0, "detail": "no file"}
            continue
        try:
            d = json.loads(path.read_text("utf-8"))
        except Exception as e:
            out[name] = {"status": "empty", "usable": False, "chars": 0, "detail": f"broken JSON: {e}"}
            continue
        out[name] = classify(d)
    return out


_GLYPH = {"ok": "✓", "legacy": "≈", "error": "✗", "empty": "∅", "missing": "—"}


def print_summary(topic: str, audit: dict) -> int:
    """Print a per-line status + summary. Returns the number of usable engines."""
    usable = 0
    for name, st in audit.items():
        g = _GLYPH.get(st["status"], "?")
        usable += 1 if st["usable"] else 0
        extra = f" — {st['detail']}" if st["detail"] else ""
        print(f"  {g} {name}: {st['status']} ({st['chars']} chars){extra}")
    print(f"[engine_status] {topic}: usable {usable}/{len(audit)}")
    return usable


def main():
    if len(sys.argv) < 2:
        print("usage: python3 funnel/engine_status.py <topic> [eng1,eng2]", file=sys.stderr)
        sys.exit(64)
    topic = sys.argv[1]
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    audit = audit_topic(topic, only)
    if not audit:
        print(f"[engine_status] {topic}: no engines (empty engines/)")
        sys.exit(2)
    usable = print_summary(topic, audit)
    sys.exit(0 if usable > 0 else 2)


if __name__ == "__main__":
    main()
