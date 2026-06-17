#!/usr/bin/env python3
"""Stage contracts for the funnel: shape of each artifact file + input/output checks.

Purpose: no stage can run without a valid result from the previous one, and no
unconfirmed fact can reach the report. Checks are here; the orchestrator (run.py)
and the guard (gate.py) call them. A failed check = StageError with a clear message.

ROOT — repository root (module lives in funnel/). Data is read from the root.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_url(s):
    return bool(_URL_RE.match((s or "").strip()))


class StageError(Exception):
    """Stage cannot run: input is missing or has wrong shape."""


# ---------- utilities ----------
def _p(*parts):
    return ROOT.joinpath(*parts)


def _load(path):
    if not path.exists():
        raise StageError(f"file missing: {path.relative_to(ROOT)}")
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as e:
        raise StageError(f"broken JSON {path.relative_to(ROOT)}: {e}")


def _need_keys(obj, keys, where):
    missing = [k for k in keys if k not in obj]
    if missing:
        raise StageError(f"{where}: missing fields {missing}")


# ---------- artifact checks (stage input/output) ----------
def validate_verdicts(topic):
    """Input for build_pool: ≥1 engine verdict with an array of claims in the required shape."""
    d = P.verdicts_dir(topic)
    files = [f for f in d.glob("*.json") if not f.stem.endswith("-core")]
    if not files:
        raise StageError(f"no verdicts in topics/{topic}/verdicts/ — run fact-checking first (check-claims)")
    for f in files:
        v = _load(f)
        if "claims" not in v or not isinstance(v["claims"], list):
            raise StageError(f"{f.name}: no claims array")
        for c in v["claims"]:
            _need_keys(c, ["id", "text", "label"], f.name)
    return len(files)


def validate_raw(topic):
    """Output of build_pool: confirmed/unconfirmed — lists of records in the required shape."""
    raw = _load(P.pool_raw(topic))
    _need_keys(raw, ["confirmed", "unconfirmed"], f"topics/{topic}/pool_raw.json")
    for bucket in ("confirmed", "unconfirmed"):
        if not isinstance(raw[bucket], list):
            raise StageError(f"topics/{topic}/pool_raw.json: {bucket} is not a list")
        for it in raw[bucket]:
            _need_keys(it, ["engine", "id", "text", "label", "source"], f"{bucket}[]")
    return {k: len(raw[k]) for k in ("confirmed", "unconfirmed")}


def validate_pool(topic, require_source_name=False):
    """Pool: facts with provenance, best source, section. require_source_name — after enrich."""
    pool = _load(P.pool(topic))
    _need_keys(pool, ["topic", "facts"], f"topics/{topic}/pool.json")
    if not pool["facts"]:
        raise StageError(f"topics/{topic}/pool.json: pool is empty — no confirmed facts")
    for i, f in enumerate(pool["facts"]):
        _need_keys(f, ["fid", "text", "anchor_id", "section", "provenance", "best_source", "best_class"], f"fact #{i}")
        if not isinstance(f["provenance"], list) or not f["provenance"]:
            raise StageError(f"fact #{i}: empty provenance")
        for p in f["provenance"]:
            _need_keys(p, ["claim_id", "text", "source", "label"], f"fact #{i} provenance")
        if require_source_name:
            for p in f["provenance"]:
                if not (p.get("source_name") or "").strip():
                    raise StageError(f"fact #{i}: source missing source_name (enrich not run or failed)")
    return len(pool["facts"])


def validate_audit(topic):
    a = _load(P.audit(topic))
    _need_keys(a, ["summary", "rows"], f"topics/{topic}/audit_rejected.json")
    return a["summary"].get("total_rejected", 0)


def validate_config(topic):
    cfg = _load(P.config(topic))
    _need_keys(cfg, ["section_order", "out", "page_title"], f"topics/{topic}/config.json")
    return cfg


def validate_report(topic, paged=False):
    cfg = _load(P.config(topic))
    rel = cfg.get("out", f"reports/REPORT-{topic}.html")
    if paged:
        # render_paged.py writes alongside as ...-paged.html (without overwriting the main report)
        rel = rel.replace(".html", "-paged.html")
    out = ROOT / rel
    if not out.exists() or out.stat().st_size < 2000:
        raise StageError(f"report not created or empty: {out}")
    return out.stat().st_size


# ---------- HARD GUARD (before printing) ----------
CONFIRMED = {"SUPPORTED", "PARTIAL"}


def is_anchor(p):
    """Strict anchor (recalculated ourselves, NOT trusting the stored is_anchor flag).

    Confirmed by the judge + link is a real URL + source is alive + not fabricated + no number correction.
    corrected ≠ empty → source confirms a different value; cannot print without a badge.
    """
    return (
        p.get("label") in CONFIRMED
        and is_url(p.get("source"))
        and p.get("source_alive") is True
        and not p.get("fabricated")
        and not (p.get("corrected") or "").strip()
    )


def is_corrected_anchor(p):
    """Anchor with a corrected number (recalculated ourselves, NOT trusting the stored is_anchor flag).

    Confirmed by the judge + live URL + not fabricated + corrected is non-empty.
    The source confirmed the substance but recorded a different specific value.
    """
    return (
        p.get("label") in CONFIRMED
        and is_url(p.get("source"))
        and p.get("source_alive") is True
        and not p.get("fabricated")
        and bool((p.get("corrected") or "").strip())
    )


def offenders_in(facts):
    """Pure guard core (no disk) — list of offending facts.

    A fact is valid for the report ⟺ best_source is a URL AND ONE of the following holds:
    A) strict path: provenance contains a strict anchor whose text verbatim == fact text,
       AND the fact does not carry a corrected field (otherwise the badge would print without verification).
    B) corrected path: provenance contains a corrected anchor whose text verbatim == fact text,
       AND fact.corrected is non-empty AND verbatim matches the anchor's corrected
       (guarantees the number from the source reached the report without substitution).

    Catches: text rewritten under a foreign link, merging different claims,
    dead/fake source, badge without a verified corrected value.
    """
    out = []
    for i, f in enumerate(facts):
        text = (f.get("text") or "").strip()
        fact_corr = (f.get("corrected") or "").strip()
        prov = f.get("provenance", [])
        no_best = not is_url(f.get("best_source"))

        # Strict path: anchor without correction + fact without corrected
        strict_ok = any(
            is_anchor(p) and (p.get("text") or "").strip() == text
            for p in prov
        ) and not fact_corr

        # Corrected path: anchor with corrected + fact.corrected matches anchor's corrected
        corrected_ok = any(
            is_corrected_anchor(p)
            and (p.get("text") or "").strip() == text
            and (p.get("corrected") or "").strip() == fact_corr
            for p in prov
        ) and bool(fact_corr)

        anchored = strict_ok or corrected_ok

        if not text or not anchored or no_best:
            if not text:
                reason = "empty text"
            elif no_best:
                reason = "best_source is not a URL"
            elif fact_corr:
                # corrected exists but no matching corrected anchor
                reason = ("corrected without a verified anchor: no corrected anchor with matching corrected"
                          " (or fact text was rewritten)")
            else:
                reason = "fact text does not match any verified anchor (rewritten/merged/no live backing)"
            out.append({"i": i, "text": text[:90], "reason": reason})
    return out


def guard_report_safe(topic):
    """Guarantee 'no hallucinations' against the pool file. Empty list = safe to print."""
    pool = _load(P.pool(topic))
    return offenders_in(pool["facts"])


def verdict_sources(topic):
    """Trusted URLs for the topic: from verdicts (source+final_source) and from re-sourcing (resourced).

    Re-sourcing (resource.js) legitimately brings NEW sources not present in verdicts —
    these are also counted as traceable, otherwise restored facts would be falsely flagged as 'bypassed'.
    """
    urls = set()
    d = P.verdicts_dir(topic)
    for f in d.glob("*.json"):
        if f.stem.endswith("-core"):
            continue
        for c in _load(f).get("claims", []):
            for k in ("source", "final_source"):
                u = (c.get(k) or "").strip()
                if u:
                    urls.add(u)
    res = P.pool_resourced(topic)
    if res.exists():
        for x in _load(res).get("results", []):
            u = (x.get("source") or "").strip()
            if u:
                urls.add(u)
    return urls


def orphans_in(facts, known):
    """Pure traceability core: facts whose sources are not in the known set (verdict sources)."""
    out = []
    for i, f in enumerate(facts):
        srcs = {(p.get("source") or "").strip() for p in f.get("provenance", [])}
        srcs |= {(f.get("best_source") or "").strip()}
        srcs.discard("")
        if not (srcs & known):
            out.append({"i": i, "text": f.get("text", "")[:90],
                        "reason": "none of the fact's sources appear in the verdicts"})
    return out


def untraceable_in_pool(topic):
    """Pool facts whose sources do NOT appear in any verdict (manual insertion bypassing the funnel)."""
    pool = _load(P.pool(topic))
    known = verdict_sources(topic)
    if not known:
        raise StageError(f"no verdicts for traceability check of topic {topic}")
    return orphans_in(pool["facts"], known)


if __name__ == "__main__":
    # quick run of all checks for a topic: python3 contracts.py <topic>
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
    print("verdicts :", validate_verdicts(topic), "engines")
    print("raw      :", validate_raw(topic))
    print("pool     :", validate_pool(topic), "facts")
    bad = guard_report_safe(topic)
    print("guard    :", "CLEAN" if not bad else f"{len(bad)} offenders")
