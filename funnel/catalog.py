#!/usr/bin/env python3
"""Generator for the catalog of all funnel topics.

Scans judge_claims/verdicts/ and runs/, collects metadata for each topic
and writes:
  - catalog.json          machine-readable catalog (repository root)
  - CATALOG.md            human-readable table (repository root)

Usage:
    python3 funnel/catalog.py
"""
import json
import os
import pathlib
import re
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path(os.environ.get("RESEARCH_VAULT", str(pathlib.Path.home() / "research-vault")))
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

# Service prefixes/suffixes that are not real topics
_SKIP_PREFIXES = ("_",)
_SKIP_SUFFIXES = ("-pilot-backup",)
_AB_RE = re.compile(r"^ab-")


def _skip_topic(name: str) -> bool:
    """Returns True if the name is not a real funnel topic."""
    if any(name.startswith(p) for p in _SKIP_PREFIXES):
        return True
    if any(name.endswith(s) for s in _SKIP_SUFFIXES):
        return True
    if _AB_RE.match(name):
        return True
    return False


def _all_topics() -> list[str]:
    """Returns a sorted list of unique topics from topics/."""
    topics: set[str] = set()
    topics_root = ROOT / "topics"
    if topics_root.exists():
        for d in topics_root.iterdir():
            if d.is_dir() and not _skip_topic(d.name):
                topics.add(d.name)
    return sorted(topics)


def _read_json(path: pathlib.Path):
    """Reads JSON; returns None on error."""
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


# ---------- topic metadata assembly ----------

def _question(topic: str) -> str:
    """First line of question.txt or fallback."""
    qp = P.question(topic)
    if qp.exists():
        try:
            line = qp.read_text("utf-8").strip().splitlines()[0].strip()
            return line if line else "?"
        except Exception:
            pass
    # Fallback: count sub-questions from facts.json
    fp = P.facts(topic)
    d = _read_json(fp)
    if d and isinstance(d, dict):
        qs = d.get("questions", d.get("sub_questions", []))
        if qs:
            return f"[{len(qs)} questions]"
    return "?"


def _rounds_engines(topic: str) -> tuple[int, list[str]]:
    """Returns (number of rounds, list of engines across all rounds)."""
    vdir = P.verdicts_dir(topic)
    if not vdir.exists():
        return 0, []
    stems = [f.stem for f in sorted(vdir.glob("*.json")) if not f.stem.endswith("-core")]
    if not stems:
        return 0, []
    # Base engines (without __rN)
    base = [s for s in stems if "__r" not in s]
    rounds = max(
        (int(re.search(r"__r(\d+)$", s).group(1)) for s in stems if "__r" in s),
        default=1,
    )
    return rounds, base


def _facts_counts(topic: str) -> tuple[int, int]:
    """Returns (confirmed_count, corrected_count) from pool _raw."""
    rp = P.pool_raw(topic)
    d = _read_json(rp)
    if not d:
        return 0, 0
    confirmed = d.get("confirmed", [])
    corrected = sum(1 for c in confirmed if (c.get("corrected") or "").strip())
    return len(confirmed), corrected


def _report_info(topic: str) -> tuple[str | None, str | None]:
    """Returns (relpath, mtime_date_str) for the topic HTML report.

    First reads topics/<topic>/config.json → out field (may have a non-standard name),
    then tries reports/REPORT-<topic>.html as a fallback.
    """
    # Priority: path from config
    cfg_p = P.config(topic)
    cfg = _read_json(cfg_p)
    if cfg:
        out_rel = cfg.get("out", f"reports/REPORT-{topic}.html")
        rp = ROOT / out_rel
        if rp.exists():
            mtime = datetime.fromtimestamp(rp.stat().st_mtime, tz=timezone.utc)
            return out_rel, mtime.strftime("%Y-%m-%d")
    # Fallback: standard name
    rp = ROOT / "reports" / f"REPORT-{topic}.html"
    if rp.exists():
        mtime = datetime.fromtimestamp(rp.stat().st_mtime, tz=timezone.utc)
        return f"reports/REPORT-{topic}.html", mtime.strftime("%Y-%m-%d")
    return None, None


def _published(topic: str) -> bool:
    """True if vault/library/research/<domain>/<topic>/ exists (in any domain)."""
    research_base = VAULT / "library" / "research"
    if not research_base.exists():
        return False
    return any((research_base / d / topic).exists()
               for d in research_base.iterdir() if d.is_dir())


def _cost_tokens(topic: str) -> dict:
    """Sums output_tokens from verdicts + ledger.jsonl lines for the topic."""
    total_tokens = 0

    # From verdicts
    vdir = P.verdicts_dir(topic)
    if vdir.exists():
        for f in sorted(vdir.glob("*.json")):
            if f.stem.endswith("-core"):
                continue
            d = _read_json(f)
            if d:
                tel = d.get("telemetry", {})
                ot = tel.get("output_tokens")
                if isinstance(ot, (int, float)):
                    total_tokens += int(ot)

    # From telemetry/ledger.jsonl
    ledger = ROOT / "telemetry" / "ledger.jsonl"
    if ledger.exists():
        try:
            for line in ledger.read_text("utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("topic") != topic:
                    continue
                for eng in row.get("engines", []):
                    ot = eng.get("output_tokens")
                    if isinstance(ot, (int, float)):
                        total_tokens += int(ot)
        except Exception:
            pass

    return {"output_tokens": total_tokens if total_tokens else None}


def _evidence_stats(topic: str) -> dict:
    """Reads topics/<topic>/evidence/index.json and returns statistics."""
    ip = P.evidence_dir(topic) / "index.json"
    if not ip.exists():
        return {"total": 0, "archived": 0, "missing": 0, "pct": None}
    index = _read_json(ip)
    if not index:
        return {"total": 0, "archived": 0, "missing": 0, "pct": None}
    total = len(index)
    archived = sum(1 for v in index.values() if v.get("file") is not None)
    missing = total - archived
    pct = round(archived / total * 100) if total else None
    return {"total": total, "archived": archived, "missing": missing, "pct": pct}


def _manifest(topic: str) -> dict | None:
    """Reads topics/<topic>/manifest.json or returns None."""
    mp = P.manifest(topic)
    return _read_json(mp)


def collect_topic(topic: str) -> dict:
    """Collects all metadata for one topic."""
    question = _question(topic)
    rounds, engines = _rounds_engines(topic)
    facts, corrected = _facts_counts(topic)
    report_path, report_date = _report_info(topic)
    pub = _published(topic)
    tokens = _cost_tokens(topic)
    evidence = _evidence_stats(topic)
    manifest = _manifest(topic)

    return {
        "topic": topic,
        "question": question,
        "rounds": rounds,
        "engines": engines,
        "facts": facts,
        "corrected": corrected,
        "report_path": report_path,
        "report_date": report_date,
        "published": pub,
        "output_tokens": tokens.get("output_tokens"),
        "evidence": evidence,
        "manifest": manifest,
    }


def _sort_key(entry: dict):
    """Sort: newest reports first, topics without a report — at the end."""
    date = entry.get("report_date")
    if date:
        return (0, date)
    return (1, entry["topic"])


def build_catalog() -> list[dict]:
    """Collects the catalog of all topics, returns a sorted list of entries."""
    topics = _all_topics()
    entries = [collect_topic(t) for t in topics]
    entries.sort(key=_sort_key, reverse=True)
    return entries


def write_catalog_json(entries: list[dict]) -> None:
    """Writes catalog.json to the repository root."""
    out = ROOT / "catalog.json"
    out.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[catalog] catalog.json → {len(entries)} topics")


def write_catalog_md(entries: list[dict]) -> None:
    """Writes CATALOG.md with the topic table."""
    lines = [
        "# Topic Catalog",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"Topics: {len(entries)}",
        "",
        "| Topic | Date | Question | Engines | Facts | Report | Published | Evidence % |",
        "|-------|------|----------|---------|-------|--------|-----------|------------|",
    ]

    for e in entries:
        topic = e["topic"]
        date = e["report_date"] or "—"
        q = e["question"]
        q_short = (q[:57] + "…") if len(q) > 60 else q
        # Remove newlines in cell
        q_short = q_short.replace("\n", " ").replace("|", "\\|")
        engines_str = ", ".join(e["engines"]) if e["engines"] else "—"
        facts_str = str(e["facts"]) if e["facts"] else "—"
        if e["corrected"]:
            facts_str += f" ({e['corrected']} corrected)"
        # Report link
        if e["report_path"]:
            report_cell = f"[HTML]({e['report_path']})"
        else:
            report_cell = "—"
        pub_cell = "yes" if e["published"] else "no"
        ev = e["evidence"]
        if ev["total"]:
            ev_cell = f"{ev['pct']}% ({ev['archived']}/{ev['total']})"
        else:
            ev_cell = "—"

        lines.append(
            f"| {topic} | {date} | {q_short} | {engines_str} | {facts_str} | {report_cell} | {pub_cell} | {ev_cell} |"
        )

    lines.append("")
    out = ROOT / "CATALOG.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[catalog] CATALOG.md updated")


def main() -> None:
    entries = build_catalog()
    write_catalog_json(entries)
    write_catalog_md(entries)


if __name__ == "__main__":
    main()
