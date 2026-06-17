#!/usr/bin/env python3
"""Assembles the fact pool from verdicts of all engines (the missing link in the funnel).

Input:  judge_claims/verdicts/<topic>/<engine>.json  (output of check_claims.js per engine)
Output: judge_claims/pool/<topic>_raw.json   — flat: confirmed / unconfirmed (for audit_rejected.py)
        judge_claims/pool/<topic>.json        — facts with provenance (for enrich_sources.py → render_final.py)

Mechanical part (deterministic, no LLM):
- confirmed   = verdict SUPPORTED or PARTIAL (fact stated and backing is alive/confirms it),
- unconfirmed = MISATTRIBUTED / UNSOURCED / BROKEN_SOURCE (cannot go into report without backing),
- draft pool: semantically identical claims from different engines are merged into one fact with provenance
  (merge by text similarity, difflib ≥ THRESHOLD; cross-language and fine semantics are handled by
  the Opus clarification step in the /research chain — it rewrites section and canonical text).

best_source is selected by class (A>B>C) and liveness. section at this step is a placeholder "Other":
it is set by the Opus clarification step from the facts themselves (topic is work-in-progress — sections not known in advance).

Anchors come in two kinds:
- strict (is_anchor): source confirmed text verbatim, corrected is empty → print as-is.
- with correction (is_corrected_anchor): source confirmed the substance but gives a different number →
  text is printed verbatim from the verdict, alongside a badge "source gives: corrected".
  The fact gets needs_review=True and a corrected field with the text from the source.

Usage: python3 build_pool.py <topic>            (default topic1)
        python3 build_pool.py <topic> --check     print summary without writing files
"""
import sys, json, glob, re, difflib, pathlib, hashlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent  # repository root (script lives in funnel/)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P
POROG = 0.82  # merge threshold for claims into one fact by normalized text similarity

CONFIRMED_LABELS = {"SUPPORTED", "PARTIAL"}
REJECTED_LABELS = {"MISATTRIBUTED", "UNSOURCED", "BROKEN_SOURCE"}
CLASS_RANK = {"A": 0, "B": 1, "C": 2, None: 3}
CONF_RANK = {"high": 0, "medium": 1, "low": 2, None: 3}


def norm(text):
    """Normalization for comparison: lowercase, no punctuation, collapsed whitespace."""
    t = (text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def load_verdicts(topic):
    """Reads all verdicts for the topic. Key — filename (stem), so additional rounds
    (e.g. perplexity_sonar__r2.json) do not overwrite the first run of the same engine."""
    out = {}
    for f in sorted(glob.glob(str(P.verdicts_dir(topic) / "*.json"))):
        stem = pathlib.Path(f).stem
        if stem.endswith("-core"):
            continue
        try:
            d = json.loads(pathlib.Path(f).read_text("utf-8"))
        except Exception as e:
            print(f"  ! skipping {stem}: {e}", file=sys.stderr)
            continue
        if "claims" not in d:
            continue
        out[stem] = {"engine": d.get("engine", stem), "claims": d["claims"]}
    return out


def to_item(src_key, engine, cl):
    """Verdict claim → pool record. src_key — verdict filename (unique across rounds)."""
    return {
        "engine": engine,
        "src_key": src_key,
        "id": cl.get("id"),
        "text": cl.get("text", ""),
        "label": cl.get("label"),
        "source": cl.get("final_source") or cl.get("source"),
        "class": cl.get("source_class"),
        "has_number": cl.get("has_number"),
        "corrected": cl.get("corrected_value"),
        "confidence": cl.get("confidence"),
        "fabricated": cl.get("fabricated"),
        "source_alive": cl.get("source_alive"),
        "quote": cl.get("quote"),
    }


def split(verdicts):
    confirmed, unconfirmed = [], []
    for stem, v in verdicts.items():
        for cl in v["claims"]:
            label = cl.get("label")
            item = to_item(stem, v["engine"], cl)
            if label in CONFIRMED_LABELS:
                confirmed.append(item)
            elif label in REJECTED_LABELS:
                unconfirmed.append(item)
            # other labels (if they appear) are silently skipped — do not go into the report
    return confirmed, unconfirmed


def cluster(confirmed):
    """Greedy merge of confirmed claims into facts by text similarity."""
    clusters = []  # each: {"norm": str-reference, "items": [item, ...]}
    for it in confirmed:
        n = norm(it["text"])
        best, best_r = None, 0.0
        for cl in clusters:
            r = difflib.SequenceMatcher(None, n, cl["norm"]).ratio()
            if r > best_r:
                best, best_r = cl, r
        if best is not None and best_r >= POROG:
            best["items"].append(it)
        else:
            clusters.append({"norm": n, "items": [it]})
    return clusters


_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_url(s):
    return bool(_URL_RE.match((s or "").strip()))


def is_anchor(it):
    """Strict anchor: confirmed, live URL, not fabricated, no number correction (corrected is empty).

    An anchor grants the right to print ITS OWN text: the source was verified by the judge on exactly this text.
    corrected ≠ empty → source confirms a DIFFERENT number; the original text cannot be printed.
    """
    return (
        it.get("label") in CONFIRMED_LABELS
        and is_url(it.get("source"))
        and it.get("source_alive") is True
        and not it.get("fabricated")
        and not (it.get("corrected") or "").strip()
    )


def is_corrected_anchor(it):
    """Anchor with a corrected number: confirmed, live URL, not fabricated, AND corrected is non-empty.

    The source confirmed the claim's substance but recorded a different specific value.
    Fact text is taken verbatim from the verdict; in the report a badge with corrected is shown alongside.
    """
    return (
        it.get("label") in CONFIRMED_LABELS
        and is_url(it.get("source"))
        and it.get("source_alive") is True
        and not it.get("fabricated")
        and bool((it.get("corrected") or "").strip())
    )


def claim_id(it):
    return f"{it.get('src_key') or it.get('engine')}:{it.get('id')}"


def fid_of(items):
    """Stable fact id = hash of its claim references. Does not change between runs with the same verdicts."""
    key = "|".join(sorted(claim_id(i) for i in items))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def to_fact(items, sections):
    """Fact from a cluster. Text — VERBATIM verified anchor (not a paraphrase). section — from sidecar by fid.

    Anchor selection order:
    1. Strict anchors (is_anchor): corrected is empty, source confirmed text exactly.
    2. Anchors with correction (is_corrected_anchor): source confirmed substance, but number differs.
       In this case the fact gets corrected=<value from source> and needs_review=True.
    3. Neither found → None (candidate for re-sourcing).
    """
    anchors = [i for i in items if is_anchor(i)]
    _select_key = lambda x: (CLASS_RANK.get(x.get("class"), 3) == 0, len(x.get("text", "")))
    use_corrected = False
    if not anchors:
        corrected_anchors = [i for i in items if is_corrected_anchor(i)]
        if not corrected_anchors:
            return None  # no verified anchor → fact is not printed (candidate for re-sourcing)
        anchors = corrected_anchors
        use_corrected = True
    anchor = max(anchors, key=_select_key)
    fid = fid_of(items)
    engines = sorted({i["engine"] for i in items})
    conf = min(items, key=lambda x: CONF_RANK.get(x.get("confidence"), 3)).get("confidence")
    corrected_value = anchor["corrected"].strip() if use_corrected else None
    return {
        "fid": fid,
        "text": anchor["text"],            # verbatim anchor — gate will verify it was not rewritten
        "corrected": corrected_value,      # None for strict anchors; value from source for corrected ones
        "anchor_id": claim_id(anchor),
        "section": sections.get(fid, "Other"),
        "provenance": [
            {
                "engine": i["engine"],
                "claim_id": claim_id(i),
                "text": i.get("text", ""),
                "source": i["source"],
                "class": i.get("class"),
                "label": i.get("label"),
                "source_alive": i.get("source_alive"),
                "fabricated": i.get("fabricated"),
                "corrected": i.get("corrected"),
                "is_anchor": is_anchor(i),
                "source_name": None,
                "source_year": None,
                "quote": i.get("quote"),
            }
            for i in items
        ],
        "best_source": anchor["source"],
        "best_class": anchor.get("class"),
        "engines_count": len(engines),
        "confidence": conf,
        "needs_review": use_corrected or any(i.get("label") == "PARTIAL" for i in items),
        "note": "",
        "best_source_name": None,
        "best_source_year": None,
        "quote": anchor.get("quote"),
    }


def load_resourced(topic):
    """Facts restored by re-sourcing → anchor records (strict contract: found + URL + class A/B + quote)."""
    p = P.pool_resourced(topic)
    if not p.exists():
        return []
    out = []
    for x in json.loads(p.read_text("utf-8")).get("results", []):
        if not x.get("found"):
            continue
        src, cls, quote = x.get("source"), x.get("source_class"), (x.get("quote") or "").strip()
        if not (is_url(src) and cls in ("A", "B") and quote):
            continue  # without a live class A/B link and verbatim quote — not trusted
        out.append({
            "engine": "resourced", "src_key": "resourced", "id": f"r{x.get('idx')}",
            "text": x.get("fact", ""), "label": "SUPPORTED", "source": src, "class": cls,
            "has_number": None, "corrected": None, "confidence": x.get("confidence", "medium"),
            "fabricated": False, "source_alive": True, "quote": quote,
        })
    return out


def load_sections(topic):
    """Section sidecar (edited by Opus clarification): {fid: section}. Fact text is NOT edited here."""
    p = P.sections(topic)
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "topic1"
    check = "--check" in sys.argv

    verdicts = load_verdicts(topic)
    if not verdicts:
        print(f"no verdicts in topics/{topic}/verdicts/ — run check_claims.js on the engines first")
        sys.exit(1)

    confirmed, unconfirmed = split(verdicts)
    recovered = load_resourced(topic)          # live anchors from re-sourcing — merged BEFORE clustering
    confirmed_all = confirmed + recovered
    sections = load_sections(topic)

    clusters = cluster(confirmed_all)
    facts, unanchored = [], 0
    for c in clusters:
        f = to_fact(c["items"], sections)
        if f:
            facts.append(f)
        else:
            unanchored += len(c["items"])      # cluster without a verified anchor — not printed
    facts.sort(key=lambda f: (-f["engines_count"], CLASS_RANK.get(f["best_class"], 3)))

    raw = {"confirmed": confirmed, "unconfirmed": unconfirmed, "recovered": recovered}
    pool = {"topic": topic, "facts": facts}

    n_corrected = sum(1 for f in facts if f.get("corrected"))
    engs = sorted({v["engine"] for v in verdicts.values()})
    print(f"topic {topic}: verdict files {len(verdicts)}, engines {len(engs)} ({', '.join(engs)})")
    print(f"  confirmed {len(confirmed)} + recovered {len(recovered)} → facts {len(facts)}")
    print(f"  of which with corrected number: {n_corrected}")
    print(f"  without verified anchor (not printed): {unanchored}")
    print(f"  unconfirmed {len(unconfirmed)} → for audit")
    print(f"  by class: {dict(Counter(f['best_class'] for f in facts))}")

    if check:
        print("(--check: files not written)")
        return

    P.topic_dir(topic).mkdir(parents=True, exist_ok=True)
    # pool is fully derived from verdicts+re-sourcing and rebuilt EACH run (no drift)
    P.pool_raw(topic).write_text(json.dumps(raw, ensure_ascii=False, indent=2), "utf-8")
    P.pool(topic).write_text(json.dumps(pool, ensure_ascii=False, indent=2), "utf-8")
    print(f"→ topics/{topic}/pool_raw.json")
    print(f"→ topics/{topic}/pool.json (sections — from sections.json, fact text unchanged)")


if __name__ == "__main__":
    main()
