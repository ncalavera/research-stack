#!/usr/bin/env python3
"""Open-access resolver: scientific URL → full text from an OA source.

Why: PubMed returns only the abstract; paywalled publishers (Springer/LWW/ScienceDirect/
Wiley/Tandfonline) return a landing page. A fact visible only in the full text is
invisible to the judge → false "not there". Here we extract DOI/PMID and fetch
the full text legally: Europe PMC fulltext → Unpaywall (OA PDF/HTML).

Input: URL. Stdout: text + last line `__OA__ via=<...> len=<n>` (exit 0), or nothing (exit 1).
Called from fetch_url.sh for scientific domains; grey access (Sci-Hub/Anna's Archive)
is NOT included here — that is a manual last resort (see architecture); this resolver
covers only legal sources.
"""
import sys, re, json, os, urllib.request, urllib.parse

EMAIL = os.environ.get("UNPAYWALL_EMAIL", "you@example.com")
TIMEOUT = 25
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
MAXLEN = 45000


def get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def getj(url, timeout=TIMEOUT):
    try:
        return json.loads(get(url, timeout))
    except Exception:
        return None


def strip_tags(t):
    t = re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    import html
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def doi_from_url(url):
    m = re.search(r"10\.\d{4,9}/[^\s?#\"'<>]+", urllib.parse.unquote(url))
    return m.group(0).rstrip(".)") if m else None


def pmid_from_url(url):
    m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", url)
    return m.group(1) if m else None


def epmc_resolve(doi=None, pmid=None):
    """Europe PMC: look up PMCID and DOI by DOI/PMID, return (pmcid, doi)."""
    q = f"DOI:{doi}" if doi else f"EXT_ID:{pmid} AND SRC:MED"
    j = getj("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query="
             + urllib.parse.quote(q) + "&format=json&pageSize=1")
    if not j:
        return None, doi
    res = (j.get("resultList") or {}).get("result") or []
    if not res:
        return None, doi
    r = res[0]
    return r.get("pmcid"), (doi or r.get("doi"))


def epmc_fulltext(pmcid):
    """Full text of an OA article from Europe PMC (fullTextXML)."""
    try:
        xml = get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML")
    except Exception:
        return None
    body = re.search(r"<body\b.*?</body>", xml, flags=re.S | re.I)
    txt = strip_tags(body.group(0) if body else xml)
    return txt if len(txt) > 600 else None


def fulltext_for(pmcid=None, doi=None, oa_url=None):
    """Full text with fallbacks: EPMC XML → PMC HTML page → Unpaywall OA → direct OA URL."""
    if pmcid:
        t = epmc_fulltext(pmcid)
        if t:
            return t, f"europepmc {pmcid}"
        t = via_jina(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
        if t:
            return (strip_tags(t) if "<" in t[:200] else t), f"pmc-html {pmcid}"
    if doi:
        oa = unpaywall(doi)
        if oa:
            t = via_jina(oa)
            if t:
                return (strip_tags(t) if "<" in t[:200] else t), f"unpaywall {oa[:50]}"
    if oa_url:
        t = via_jina(oa_url)
        if t:
            return (strip_tags(t) if "<" in t[:200] else t), f"oa {oa_url[:50]}"
    return None, None


def unpaywall(doi):
    """Unpaywall: best OA URL for a given DOI (PDF or repository landing page HTML)."""
    j = getj(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={EMAIL}")
    if not j:
        return None
    loc = j.get("best_oa_location") or {}
    return loc.get("url_for_pdf") or loc.get("url") or loc.get("url_for_landing_page")


def via_jina(url):
    """Fetch an OA page/PDF via r.jina.ai (supports PDF)."""
    try:
        t = get("https://r.jina.ai/" + url, timeout=30)
        return t if len(t) > 600 else None
    except Exception:
        return None


def resolve(url):
    doi = doi_from_url(url)
    pmid = pmid_from_url(url)
    # 1) Europe PMC fulltext (cleanest full text for OA)
    pmcid, doi = epmc_resolve(doi=doi, pmid=pmid)
    if pmcid:
        t = epmc_fulltext(pmcid)
        if t:
            return t[:MAXLEN], f"europepmc {pmcid}"
    # 2) Unpaywall by DOI → OA PDF/HTML → fetch via jina
    if doi:
        oa = unpaywall(doi)
        if oa:
            t = via_jina(oa)
            if t:
                return strip_tags(t)[:MAXLEN] if "<" in t[:200] else t[:MAXLEN], f"unpaywall {oa[:60]}"
    return None, None


def search_oa(query, limit=6):
    """Re-sourcing (step 5): search for an OA article by fact topic and fetch its full text.
    Semantic Scholar (relevance + openAccessPdf) → Europe PMC (OA fulltext).
    Returns [{title, year, doi, source, oa_url}] candidates + text of the best with full text."""
    cands = []
    # 1) Semantic Scholar Graph API (no key required, rate-limited)
    ss = getj("https://api.semanticscholar.org/graph/v1/paper/search?"
              + urllib.parse.urlencode({"query": query, "limit": limit,
                "fields": "title,year,externalIds,openAccessPdf,abstract"}))
    for p in (ss or {}).get("data", []) or []:
        oa = (p.get("openAccessPdf") or {}).get("url")
        cands.append({"title": p.get("title"), "year": p.get("year"),
                      "doi": (p.get("externalIds") or {}).get("DOI"),
                      "oa_url": oa, "source": "semanticscholar",
                      "abstract": (p.get("abstract") or "")[:600]})
    # 2) Europe PMC, open access only
    ep = getj("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query="
              + urllib.parse.quote(f"({query}) AND OPEN_ACCESS:Y") + "&format=json&pageSize=" + str(limit))
    for r in ((ep or {}).get("resultList") or {}).get("result", []) or []:
        cands.append({"title": r.get("title"), "year": r.get("pubYear"),
                      "doi": r.get("doi"), "pmcid": r.get("pmcid"),
                      "oa_url": None, "source": "europepmc",
                      "abstract": (r.get("abstractText") or "")[:600]})
    # fetch full text for the first candidate that succeeds
    best_text, best = None, None
    for c in cands:
        t, via = fulltext_for(pmcid=c.get("pmcid"), doi=c.get("doi"), oa_url=c.get("oa_url"))
        if t:
            c["via"] = via
            best_text, best = t[:MAXLEN], c
            break
    return cands, best, best_text


if __name__ == "__main__":
    # re-sourcing mode: resolve_oa.py --search "fact topic"
    if len(sys.argv) >= 3 and sys.argv[1] == "--search":
        cands, best, text = search_oa(sys.argv[2])
        out = {"candidates": [{k: v for k, v in c.items() if k != "abstract"} for c in cands[:6]],
               "best": ({k: v for k, v in best.items() if k != "abstract"} if best else None),
               "fulltext": text}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(0 if text else 1)
    if len(sys.argv) < 2:
        sys.exit(1)
    try:
        text, via = resolve(sys.argv[1])
    except Exception as e:
        sys.stderr.write(f"resolve_oa error: {e}\n")
        sys.exit(1)
    if text:
        print(text)
        # pipeline marker: the core treats __SOURCE__ as "page is alive"
        print(f"__SOURCE__ oa via={via} len={len(text)}")
        sys.exit(0)
    sys.exit(1)
