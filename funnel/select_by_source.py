#!/usr/bin/env python3
"""select_by_source — "golden mean" selection between coverage and cost.

Problem with two extremes:
  • top-5 atoms per question (manual cutoff) → a corroborated source can
    fall below the threshold and be lost (case 14.06.2026: review S1440244021001080
    found by 3 engines but did not fit in top-5 and never reached the pool);
  • checking all 158 atoms → expensive and pointless: five engines paraphrase
    one conclusion from one paper in different words.

Key to cost: the judge in check_claims works on SOURCE GROUPS — one agent per one
URL with all its atoms. So cost ≈ number of DISTINCT links, not atoms. Therefore:
  1. group atoms by normalized link;
  2. within a link keep all SEMANTICALLY DISTINCT facts (sample size, effect size,
     conclusion — these are different facts), discard only verbatim repeats across
     engines (close text at the same link);
  3. ALL sources go to verification, with no top cutoff.

So no source is lost, and verification does not inflate on duplicates.
Output: topics/<topic>/select_by_source.json = {engine: [ {id,text,source,has_number}, ... ]}
— ready batches for check_claims (by engine). Prints selection statistics.
"""
import json
import os
import pathlib
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

# Text similarity threshold (Jaccard on words): above this — counts as a repeat of one idea.
# 0.6 catches paraphrases of one conclusion across engines, does not touch different facts
# from one paper (sample / effect / conclusion are usually <0.5 by words).
DUP_THRESHOLD = 0.6


def norm_src(url: str) -> str:
    """Normalize URL to article (PMC/PubMed/DOI/PII), remove #fragment and query —
    same as in coverage_audit, so grouping matches."""
    if not url:
        return ""
    u = url.strip().lower().split("#")[0].split("?")[0].rstrip("/")
    for pat, pref in (
        (r"(pmc\d{6,})", "pmc:"),
        (r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{6,})", "pmid:"),
        (r"(10\.\d{4,}/[^\s]+)", "doi:"),
        (r"/pii/([a-z0-9]+)", "pii:"),
    ):
        m = re.search(pat, u)
        if m:
            return pref + m.group(1)
    return u


_word = re.compile(r"[a-zа-я0-9]+")


def toks(text: str) -> set:
    return set(_word.findall((text or "").lower()))


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_atoms(topic):
    d = P.atoms_dir(topic)
    out = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            out[f[:-5]] = json.load(open(os.path.join(d, f)))
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: select_by_source.py <topic> [--json]", file=sys.stderr)
        sys.exit(1)
    topic = sys.argv[1]
    as_json = "--json" in sys.argv

    atoms = load_atoms(topic)

    # Collect all atoms with a link: (engine, claim) under their normalized source.
    by_src = defaultdict(list)  # norm_src → [ {engine,id,text,source,has_number,toks} ]
    total_sourced = 0
    for engine, d in atoms.items():
        for c in d.get("claims", []):
            url = c.get("source") or c.get("url")
            if not url:
                continue  # nothing to verify without a link — not our case
            total_sourced += 1
            key = norm_src(url)
            by_src[key].append({
                "engine": engine, "id": c["id"], "text": c.get("text", ""),
                "source": url, "has_number": bool(c.get("has_number")),
                "_toks": toks(c.get("text", "")),
            })

    # Within each source, discard verbatim repeats (close text).
    # From a duplicate cluster, keep the strongest: with number > longer text.
    kept = []  # selected atoms
    dropped = 0
    for key, group in by_src.items():
        reps = []  # representative clusters for this source
        for a in group:
            dup_of = None
            for r in reps:
                if jaccard(a["_toks"], r["_toks"]) >= DUP_THRESHOLD:
                    dup_of = r
                    break
            if dup_of is None:
                a["_corro"] = {a["engine"]}
                reps.append(a)
            else:
                dup_of["_corro"].add(a["engine"])
                dropped += 1
                # if the new one is stronger (number / longer) — it becomes the representative
                better = (a["has_number"] and not dup_of["has_number"]) or (
                    a["has_number"] == dup_of["has_number"]
                    and len(a["text"]) > len(dup_of["text"])
                )
                if better:
                    a["_corro"] = dup_of["_corro"]
                    reps[reps.index(dup_of)] = a
        kept.extend(reps)

    # Split selected by engine for check_claims (full objects).
    batches = defaultdict(list)
    for a in kept:
        batches[a["engine"]].append({
            "id": a["id"], "text": a["text"],
            "source": a["source"], "has_number": a["has_number"],
        })

    out_path = str(P.select_by_source(topic))
    json.dump(dict(batches), open(out_path, "w"), ensure_ascii=False, indent=2)

    stats = {
        "topic": topic,
        "atoms_sourced": total_sourced,
        "distinct_sources": len(by_src),
        "kept": len(kept),
        "dropped_duplicates": dropped,
        "batches_by_engine": {e: len(v) for e, v in batches.items()},
        "out": out_path,
    }
    if as_json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    print(f"[select_by_source] topic {topic}: atoms with link {total_sourced} → "
          f"distinct sources {len(by_src)} → for verification {len(kept)} "
          f"(dropped verbatim duplicates {dropped})")
    print(f"  by engine: " + ", ".join(f"{e}:{n}" for e, n in stats["batches_by_engine"].items()))
    print(f"→ {out_path}")
    print("  next: check_claims for each engine with these ids (round 1), then build_pool.")


if __name__ == "__main__":
    main()
