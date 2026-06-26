#!/usr/bin/env python3
"""coverage_audit — count audit: how many DISTINCT sources the engines found and
how many actually reached the pool. Catches silent under-coverage when a question is marked
"covered" (at least one fact exists) but unique journal papers were left
unchecked — case 14.06.2026: Nuuttila / tracker / speed-based autoregulation
were found by engines but did not make it into the first-round pool.

Under-coverage signal: a journal source is present in raw atoms (especially from ≥2
engines) but absent from pool.json. Soft stage: warns, does not kill the build.
Exit 2 — under-coverage detected (another verification round needed), 0 — coverage complete.
"""
import json
import os
import pathlib
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

# Hosts of peer-reviewed journals / primary sources. Blogs (medium.com,
# industry blogs, reddit...) are NOT included — their under-coverage is not counted.
JOURNAL_HOSTS = (
    "ncbi.nlm.nih.gov", "pubmed.ncbi", "pmc.ncbi", "nih.gov",
    "sagepub.com", "journals.sagepub", "sciencedirect.com", "nature.com",
    "springer.com", "link.springer", "bmj.com", "bjsm.bmj", "bmjopen.bmj",
    "frontiersin.org", "mdpi.com", "jhse.es", "apcz.umk.pl", "academic.oup",
    "tandfonline.com", "onlinelibrary.wiley", "jamanetwork.com", "doi.org",
    "semanticscholar.org", "arxiv.org", "physoc.onlinelibrary",
)


def is_journal(url: str) -> bool:
    return bool(url) and any(h in url for h in JOURNAL_HOSTS)


def norm(url: str) -> str:
    """Normalize URL to article: remove #fragment, query, trailing slash,
    canonicalize PMC/PubMed id — so that PMC8507742 and
    PMC8507742/#:~:text=… count as the same source."""
    if not url:
        return ""
    u = url.strip().lower().split("#")[0].split("?")[0].rstrip("/")
    m = re.search(r"(pmc\d{6,})", u)
    if m:
        return "pmc:" + m.group(1)
    m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{6,})", u)
    if m:
        return "pmid:" + m.group(1)
    m = re.search(r"(10\.\d{4,}/[^\s]+)", u)  # doi
    if m:
        return "doi:" + m.group(1)
    m = re.search(r"/pii/([a-z0-9]+)", u)
    if m:
        return "pii:" + m.group(1)
    return u


def load_atoms(topic):
    d = P.atoms_dir(topic)
    out = {}
    if not os.path.isdir(d):
        return out
    for f in os.listdir(d):
        if f.endswith(".json"):
            out[f[:-5]] = json.load(open(os.path.join(d, f)))
    return out


def load_pool(topic):
    p = P.pool(topic)
    if not os.path.exists(p):
        return []
    d = json.load(open(p))
    return d if isinstance(d, list) else d.get("facts", [])


def main():
    if len(sys.argv) < 2:
        print("usage: coverage_audit.py <topic> [--json]", file=sys.stderr)
        sys.exit(1)
    topic = sys.argv[1]
    as_json = "--json" in sys.argv

    atoms = load_atoms(topic)
    pool = load_pool(topic)

    # Sources in raw atoms: norm-url → {engines:set, atoms:int, text}
    src = defaultdict(lambda: {"engines": set(), "atoms": 0, "text": "", "raw": ""})
    total_atoms = 0
    for engine, d in atoms.items():
        for c in d.get("claims", []):
            total_atoms += 1
            u = c.get("source") or c.get("url") or ""
            if not is_journal(u):
                continue
            key = norm(u)
            src[key]["engines"].add(engine)
            src[key]["atoms"] += 1
            if not src[key]["text"]:
                src[key]["text"] = (c.get("text") or "")[:120]
                src[key]["raw"] = u

    # Sources that made it to the pool
    pool_src = set()
    for f in pool:
        u = f.get("best_source") or f.get("anchor_url") or ""
        if u:
            pool_src.add(norm(u))

    journal_total = set(src.keys())
    covered = journal_total & pool_src
    missed = journal_total - pool_src

    # Rank missed by engine count (corroboration = signal strength)
    missed_rows = sorted(
        ({"src": k, "engines": len(src[k]["engines"]),
          "engine_list": sorted(src[k]["engines"]),
          "atoms": src[k]["atoms"], "text": src[k]["text"], "url": src[k]["raw"]}
         for k in missed),
        key=lambda r: (-r["engines"], -r["atoms"]),
    )
    corroborated_missed = [r for r in missed_rows if r["engines"] >= 2]

    ratio = (len(covered) / len(journal_total)) if journal_total else 1.0
    # Under-coverage flag: a journal source missed by ≥2 engines, OR coverage <60%
    flagged = bool(corroborated_missed) or (journal_total and ratio < 0.60)

    summary = {
        "topic": topic,
        "atoms_total": total_atoms,
        "journal_sources_total": len(journal_total),
        "journal_sources_in_pool": len(covered),
        "journal_sources_missed": len(missed),
        "coverage_ratio": round(ratio, 2),
        "corroborated_missed": corroborated_missed,
        "missed": missed_rows,
        "flagged": flagged,
    }

    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        sys.exit(2 if flagged else 0)

    print(f"[coverage] topic {topic}: atoms {total_atoms}, "
          f"distinct journal sources {len(journal_total)} → "
          f"in pool {len(covered)} ({int(ratio * 100)}%), missed {len(missed)}")
    if corroborated_missed:
        print(f"⚠ UNDER-COVERAGE: {len(corroborated_missed)} journal source(s) "
              f"found by ≥2 engines but NOT in pool — another verification round needed:")
        for r in corroborated_missed:
            print(f"   • {r['src']} (engines: {r['engines']}, "
                  f"{', '.join(r['engine_list'])}) — {r['text']}")
    elif missed_rows:
        print(f"   missed (single engine, weak signal): "
              f"{', '.join(r['src'] for r in missed_rows[:8])}"
              + (" …" if len(missed_rows) > 8 else ""))
    if flagged:
        print("→ verdict: NEEDS MORE COVERAGE. Run round 2 verification on missed sources "
              "(check_claims with __rN suffix), rebuild pool.")
    else:
        print("→ verdict: coverage complete, no under-coverage.")

    sys.exit(2 if flagged else 0)


if __name__ == "__main__":
    main()
