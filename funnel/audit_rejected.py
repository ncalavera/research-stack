#!/usr/bin/env python3
"""Audit of fairness of rejected facts.

Joins rejected facts (topics/<topic>/pool_raw.json → unconfirmed)
with full justification from engine verdicts (topics/<topic>/verdicts/<engine>.json),
classifies rejection fairness and marks candidates for recovery.

Fairness logic (fair_reject):
- UNSOURCED      — engine gave no source → rejection FAIR (cannot go into report without backing).
- MISATTRIBUTED  — source was alive and accessible, fact not found on it → rejection FAIR
                   (quote genuinely does not confirm; validated by a sample of 26 live pages).
- BROKEN_SOURCE  — AMBIGUOUS. We split by cause of "death":
    * fetch failure (reCAPTCHA / paywall / abstract-only / JS-SPA / bot-block),
      and the judge note contains a signal that the fact IS genuinely confirmed (Sonnet SUPPORTED,
      OA full-text, WebSearch confirmed) → rejection INCORRECT (false negative, fetch gap).
    * actual death (404, opaque vertexaisearch redirect, no traces of confirmation) → FAIR.

recoverable (re-sourcing candidate): fact is valuable (not local arithmetic/context-dependent)
and potentially true — for all incorrectly rejected + valuable unsourced.
"""
import json
import re
import sys
import pathlib
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent  # repository root (script in funnel/)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

ENGINES = [
    "claude_deepresearch", "openai_deep", "perplexity_deep",
    "perplexity_sonar", "exa_research", "exa_answer",
]

# Markers of fetch failure in the judge note (not actual source death)
RETRIEVAL_FAIL = [
    "recaptcha", "checking your browser", "captcha", "cloudflare",
    "paywall", "abstract", "full text",
    "bot", "403", "javascript", "js-spa", "salesforce",
    "available and confirms", "confirmed by websearch", "confirms the range",
    "fulltext", "oa-", "open access",
]
# Markers of actual death
REAL_DEAD = [
    "vertexaisearch", "404", "not found", "opaque", "redirect",
    "does not exist", "empty page", "no trace", "fabricat",
]


def load_verdict_notes(topic):
    """(engine,id) -> {note, disagreement, source_alive, source_class, tier, escalated}"""
    notes = {}
    for eng in ENGINES:
        path = P.verdicts_dir(topic) / f"{eng}.json"
        try:
            d = json.load(open(path))
        except FileNotFoundError:
            continue
        for c in d.get("claims", []):
            notes[(eng, c["id"])] = {
                "note": c.get("note", ""),
                "disagreement": c.get("disagreement"),
                "counter": c.get("counter"),
                "source_alive": c.get("source_alive"),
                "source_class": c.get("source_class"),
                "tier": c.get("tier"),
                "escalated": c.get("escalated"),
            }
    return notes


# Manual audit overrides are taken from the optional `topics/<topic>/audit_overrides.json`,
# if it exists; empty by default.
# Record format: (engine, id) -> (fair_reject: bool, recoverable: bool, why: str)
# Vendor domains returning 403 due to an auth wall are counted as BROKEN_SOURCE
# (not actual source death); rejection fairness is ambiguous.
BROKEN_OVERRIDE: dict = {}


def classify_broken(fact, vnote):
    """Returns (fair_reject, why) for BROKEN_SOURCE based on manual overrides."""
    o = BROKEN_OVERRIDE.get((fact["engine"], fact["id"]))
    if o:
        return o[0], o[2]
    return None, "ambiguous — no manual override"


# arithmetic/local context — not a generally significant fact, no point in recovering
NOISE_PAT = re.compile(
    r"\btarget\b.*\bvalue\b|\bstarting\b.*\bvalue\b",
    re.IGNORECASE,
)


def is_recoverable(fact):
    """Valuable generally significant fact (not local arithmetic for personal data)."""
    t = fact["text"]
    if NOISE_PAT.search(t):
        return False
    return True


def audit(topic):
    raw = json.load(open(P.pool_raw(topic)))
    notes = load_verdict_notes(topic)
    rejected = raw["unconfirmed"]

    rows = []
    for f in rejected:
        key = (f["engine"], f["id"])
        vnote = notes.get(key, {})
        label = f["label"]
        rec_override = None
        if label == "UNSOURCED":
            fair, why = True, "source not provided — cannot go into report without backing"
        elif label == "MISATTRIBUTED":
            fair, why = True, "source is alive but fact not found on it (sample of 26 confirmed correctness)"
        elif label == "BROKEN_SOURCE":
            fair, why = classify_broken(f, vnote)
            o = BROKEN_OVERRIDE.get((f["engine"], f["id"]))
            if o:
                rec_override = o[1]
        else:
            fair, why = None, "unknown label"

        rows.append({
            "engine": f["engine"],
            "id": f["id"],
            "text": f["text"],
            "label": label,
            "source": f.get("source"),
            "source_alive": vnote.get("source_alive"),
            "source_class": vnote.get("source_class"),
            "has_number": f.get("has_number"),
            "tier": vnote.get("tier"),
            "fair_reject": fair,
            "fair_why": why,
            "recoverable": rec_override if rec_override is not None else is_recoverable(f),
            "judge_note": vnote.get("note", ""),
            "sonnet_view": (vnote.get("disagreement") or {}).get("sonnet")
                if isinstance(vnote.get("disagreement"), dict) else None,
        })

    # statistics
    n = len(rows)
    fair = sum(1 for r in rows if r["fair_reject"] is True)
    wrong = sum(1 for r in rows if r["fair_reject"] is False)
    unclear = sum(1 for r in rows if r["fair_reject"] is None)
    rec_targets = [r for r in rows if r["recoverable"] and (r["fair_reject"] is False or r["label"] in ("UNSOURCED", "MISATTRIBUTED") or r["fair_reject"] is None)]

    summary = {
        "topic": topic,
        "total_rejected": n,
        "by_label": dict(Counter(r["label"] for r in rows)),
        "fair_reject": fair,
        "wrong_reject": wrong,
        "unclear": unclear,
        "fair_share_pct": round(100 * fair / n) if n else 0,
        "wrong_by_label": dict(Counter(r["label"] for r in rows if r["fair_reject"] is False)),
        "recovery_candidates": len(rec_targets),
    }
    return {"summary": summary, "rows": rows, "recovery_candidates": rec_targets}


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
    out = audit(topic)
    P.audit(topic).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(P.audit(topic), "w"),
              ensure_ascii=False, indent=2)
    s = out["summary"]
    print(json.dumps(s, ensure_ascii=False, indent=2))
    print(f"\n→ topics/{topic}/audit_rejected.json")
