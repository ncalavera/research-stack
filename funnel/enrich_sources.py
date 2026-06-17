#!/usr/bin/env python3
"""Source enrichment for layout: URL → readable name + publication year.

Year is taken honestly: from the URL (regex) or from NCBI E-utilities for PMC/PubMed.
If year cannot be extracted — left as null (not fabricated).
Output: source_meta.json {url: {name, year}}
"""
import json, re, time, pathlib, urllib.request, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent  # repository root (script lives in funnel/)
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P
TOPIC = sys.argv[1] if len(sys.argv) > 1 else "topic1"
FACTS = json.loads(P.pool(TOPIC).read_text("utf-8"))["facts"]

# domain → readable publisher/source name
# The initial dictionary covers common scientific and news domains.
# enrich_sources.py extends it from provenance data on each run.
NAME = {
    "pmc.ncbi.nlm.nih.gov": "PubMed Central",
    "pubmed.ncbi.nlm.nih.gov": "PubMed",
    "ncbi.nlm.nih.gov": "NCBI Bookshelf",
    "frontiersin.org": "Frontiers",
    "journals.plos.org": "PLOS ONE",
    "nature.com": "Nature",
    "tandfonline.com": "Taylor & Francis",
    "link.springer.com": "Springer",
    "cyberleninka.ru": "CyberLeninka",
}


def domain(url):
    try:
        return url.split("/")[2].replace("www.", "")
    except Exception:
        return url


def name_of(url):
    return NAME.get(domain(url), domain(url))


def year_from_url(url):
    m = re.search(r"/((?:19|20)\d\d)[/-]", url)
    if m:
        return m.group(1)
    m = re.search(r"-(20\d\d)\d+", url)  # mayo art-20048065 → NOT a year, skip these
    return None


def ncbi_year(db, uid):
    """esummary → publication year (pubdate). Network; silently returns None on failure."""
    try:
        url = (f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
               f"db={db}&id={uid}&retmode=json")
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        res = data.get("result", {}).get(uid, {})
        for key in ("pubdate", "epubdate", "sortpubdate", "printpubdate"):
            v = res.get(key)
            if v:
                m = re.search(r"(19|20)\d\d", v)
                if m:
                    return m.group(0)
    except Exception:
        return None
    return None


# collect unique sources
urls = []
for f in FACTS:
    for p in f["provenance"]:
        if p["source"] not in urls:
            urls.append(p["source"])

# network cache to avoid repeated NCBI calls
CACHE_PATH = ROOT / "source_meta.json"
cache = json.loads(CACHE_PATH.read_text("utf-8")) if CACHE_PATH.exists() else {}

meta = {}
for u in urls:
    if u in cache and cache[u].get("name"):
        meta[u] = cache[u]
        continue
    yr = year_from_url(u)
    dom = domain(u)
    if not yr and dom == "pmc.ncbi.nlm.nih.gov":
        m = re.search(r"PMC(\d+)", u)
        if m:
            yr = ncbi_year("pmc", m.group(1)); time.sleep(0.34)
    elif not yr and dom == "pubmed.ncbi.nlm.nih.gov":
        m = re.search(r"/(\d+)", u)
        if m:
            yr = ncbi_year("pubmed", m.group(1)); time.sleep(0.34)
    meta[u] = {"name": name_of(u), "year": yr}

merged = {**cache, **meta}  # do not lose sources from other topics
CACHE_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")

# --- embed name+year directly into the pool (each provenance entry + fact best source) ---
POOL_PATH = P.pool(TOPIC)
pool = json.loads(POOL_PATH.read_text("utf-8"))
for f in pool["facts"]:
    for p in f["provenance"]:
        m = meta.get(p["source"], {})
        p["source_name"] = m.get("name") or domain(p["source"])
        p["source_year"] = m.get("year")
    bm = meta.get(f.get("best_source"), {})
    f["best_source_name"] = bm.get("name") or domain(f.get("best_source", ""))
    f["best_source_year"] = bm.get("year")
POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")

n_year = sum(1 for v in meta.values() if v["year"])
print(f"sources: {len(meta)}, with year: {n_year}; year embedded in {POOL_PATH.name}")
