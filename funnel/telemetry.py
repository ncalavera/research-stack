#!/usr/bin/env python3
"""Run telemetry: reads artifacts for one topic and appends one JSON line to
telemetry/ledger.jsonl (creates the directory if needed).

Usage: python3 funnel/telemetry.py <topic>

One call = one line in the log. Intentional non-idempotency: run.py calls this
script after each run, lines accumulate — this is by design for dynamics analysis.
"""
import json
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent  # repository root (script in funnel/)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P


def _read_json(path):
    """Reads a JSON file; returns None if file is missing or broken."""
    try:
        return json.loads(pathlib.Path(path).read_text("utf-8"))
    except Exception:
        return None


def _read_verdicts(topic):
    """Reads all verdicts for the topic (skips *-core). Returns list of dicts with engine-level fields."""
    rows = []
    vdir = P.verdicts_dir(topic)
    if not vdir.exists():
        return rows
    for f in sorted(vdir.glob("*.json")):
        if f.stem.endswith("-core"):
            continue
        d = _read_json(f)
        if not d or "claims" not in d:
            continue
        claims = d.get("claims", [])
        tally = d.get("tally", {})
        # if tally is not recorded in the file — recalculate from claims
        if not tally:
            for c in claims:
                lbl = c.get("label")
                if lbl:
                    tally[lbl] = tally.get(lbl, 0) + 1
        # telemetry from the telemetry block (present in new runs), otherwise null
        tel = d.get("telemetry", {})
        rows.append({
            "engine": d.get("engine", f.stem),
            "src_key": f.stem,
            "n_claims": len(claims),
            "labels": tally,
            "opus_used": d.get("opus_used", tel.get("opus_used")),
            "counter_flips": d.get("counter_flips", tel.get("counter_flips")),
            "escalated": tel.get("escalated"),        # null for old files
            "output_tokens": tel.get("output_tokens"),  # null for old files
        })
    return rows


def _read_pool(topic):
    """Reads topics/<topic>/pool_raw.json and topics/<topic>/pool.json, returns aggregates."""
    raw = _read_json(P.pool_raw(topic))
    pool = _read_json(P.pool(topic))

    confirmed = raw.get("confirmed", []) if raw else []
    unconfirmed = raw.get("unconfirmed", []) if raw else []
    recovered = raw.get("recovered", []) if raw else []

    # corrected_facts: confirmed with non-empty "corrected" field (PARTIAL — number corrected)
    corrected_facts = sum(1 for c in confirmed if (c.get("corrected") or "").strip())

    # engines_count_avg: average number of engines in fact provenance (coverage measure)
    facts = (pool.get("facts", []) if pool else [])
    if facts:
        avg_eng = round(
            sum(len({p.get("engine") for p in f.get("provenance", [])}) for f in facts)
            / len(facts),
            2,
        )
    else:
        avg_eng = None

    return {
        "facts": len(confirmed),
        "corrected_facts": corrected_facts,
        "engines_count_avg": avg_eng,
    }, {
        "confirmed": len(confirmed),
        "unconfirmed": len(unconfirmed),
        "recovered": len(recovered),
    }


def _read_audit(topic):
    """Reads topics/<topic>/audit_rejected.json. Returns dict or None."""
    d = _read_json(P.audit(topic))
    if not d:
        return {"total_rejected": None}
    summary = d.get("summary", {})
    return {"total_rejected": summary.get("total_rejected")}


def _gate_offenders(topic):
    """Counts guard offenders via contracts.guard_report_safe. Returns int or None."""
    try:
        import contracts
        offenders = contracts.guard_report_safe(topic)
        return len(offenders)
    except Exception:
        return None


def _report_bytes(topic):
    """HTML report size in bytes, or None if missing."""
    cfg = _read_json(P.config(topic))
    if not cfg:
        return None
    out_path = ROOT / cfg.get("out", f"reports/REPORT-{topic}.html")
    try:
        return out_path.stat().st_size
    except Exception:
        return None


def collect(topic):
    """Collects telemetry for the topic and returns a dict for one log line."""
    engines = _read_verdicts(topic)
    pool_agg, raw_agg = _read_pool(topic)
    audit_agg = _read_audit(topic)
    gate_off = _gate_offenders(topic)
    rep_bytes = _report_bytes(topic)

    return {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "topic": topic,
        "engines": engines,
        "pool": pool_agg,
        "raw": raw_agg,
        "audit": audit_agg,
        "gate_offenders": gate_off,
        "report_bytes": rep_bytes,
    }


def main():
    if len(sys.argv) < 2:
        print("topic required: python3 funnel/telemetry.py <topic>")
        sys.exit(2)
    topic = sys.argv[1]

    row = collect(topic)

    # append to telemetry/ledger.jsonl (create directory if missing)
    ledger_dir = ROOT / "telemetry"
    ledger_dir.mkdir(exist_ok=True)
    ledger_path = ledger_dir / "ledger.jsonl"
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # one-line summary
    n_eng = len(row["engines"])
    n_facts = row["pool"]["facts"]
    n_raw = row["raw"]["confirmed"] + row["raw"]["unconfirmed"]
    gate = row["gate_offenders"]
    gate_str = f"gate={gate}" if gate is not None else "gate=?"
    rep = f"report={row['report_bytes']//1024}KB" if row["report_bytes"] else "report=none"
    print(
        f"[telemetry] {topic} | engines={n_eng} | facts={n_facts} | raw={n_raw} | "
        f"{gate_str} | {rep} → {ledger_path.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
