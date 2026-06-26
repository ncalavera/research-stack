#!/usr/bin/env python3
"""Final report rendering: verified fact pool from the funnel → magazine-style HTML.

Universal renderer: topic is passed as an argument; all topic-specific data lives in the topic config.
  judge_claims/pool/<topic>.json          — all confirmed facts (per-engine provenance)
  judge_claims/audit/<topic>_rejected.json — rejected claims → "To review" block (optional)
  reports/<topic>.config.json             — title, dek, intro, section order, footer (optional)
  <narratives_file from config>           — prose per section + so_what (optional)
  <profile_file from config>              — personalisation (optional)
  source_meta.json                        — source name+year (populated by enrich_sources.py)

Any missing piece → renderer degrades gracefully (no narrative/personalisation/review block).
Design system: improv-tovarisch v2.1 (spirit of Stripe Press / Lapham's Quarterly):
warm monochrome palette, Commissioner / Onest / JetBrains Mono / Caveat, fluid type scale,
source class and confidence encoded by shape and weight, not colour. Light/dark themes, print.

Usage: python3 render_final.py <topic>            (default: topic1)
Output: reports/REPORT-<topic>.html               (or "out" from config)
"""
import sys, json, html, pathlib, datetime, re

_CURRENT_YEAR = datetime.date.today().year

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT / "funnel"))
import paths as P
TOPIC = sys.argv[1] if len(sys.argv) > 1 else "topic1"


# ---------- contradictions sidecar helpers (testable without executing main) ----------

def load_contradictions(topic, root=None):
    """Load contradictions sidecar for a topic. Returns None if absent (feature off)."""
    p = P.contradictions(topic)
    if not p.exists():
        return None
    return json.loads(p.read_text("utf-8"))


def partition_facts(facts, contradictions_data):
    """Partition facts into (standalone_fids: set, groups: list[dict]).

    standalone_fids — fids that render as normal cards (not in any valid contradiction group).
    groups — contradiction groups where every fid resolved to a known fact; groups with <2
             valid fids degrade to standalone (their fids go to standalone_fids instead).
    Unknown fids in the sidecar print a warning to stdout and are silently skipped.

    contradictions_data=None → all facts are standalone (feature off).
    """
    if not contradictions_data:
        return {f["fid"] for f in facts}, []

    fid_to_fact = {f["fid"]: f for f in facts}
    groups_out = []
    grouped_fids = set()

    for grp in contradictions_data.get("groups", []):
        valid, bad = [], []
        for fid in grp.get("fids", []):
            if fid in fid_to_fact:
                valid.append(fid)
            else:
                bad.append(fid)
        for fid in bad:
            print(f"⚠ contradictions: unknown fid {fid} (group {grp.get('gid','?')}) — skipping")
        if len(valid) >= 2:
            groups_out.append({**grp, "fids": valid})
            grouped_fids.update(valid)
        else:
            # degrade: <2 valid → standalone (no warning needed, bad fids already warned above)
            pass

    standalone_fids = {f["fid"] for f in facts} - grouped_fids
    return standalone_fids, groups_out


def load(path, default):
    p = pathlib.Path(path)
    return json.loads(p.read_text("utf-8")) if p.exists() else default


# Shared rendering helpers. Imported here (after `def load`) rather than at the
# top so test_funnel.py can exec the file's prefix up to `def load` in isolation.
from render_final_css import STYLE_CSS
from render_common import (esc, domain, _num, _pos, _ZONE_BAND,
                           _viz_stacked, _viz_dots, _viz_timeline, _viz_bands,
                           _viz_bars, _viz_line, _viz_donut, _VIZ)

CFG = load(P.config(TOPIC), {})


def cfg(key, default=""):
    return CFG.get(key, default)


POOL = json.loads(P.pool(TOPIC).read_text("utf-8"))
REJ = load(P.audit(TOPIC),
           {"summary": {}, "rows": [], "recovery_candidates": []})
NARR = load(ROOT / cfg("narratives_file", str(P.narratives(TOPIC).relative_to(ROOT))), {})
SO_WHAT = NARR.get("_so_what", {})
KEYPOINTS = NARR.get("_keypoints", {})
TABLES = NARR.get("_tables", {})
ACTION_PLAN = NARR.get("_action_plan", [])
INFOGRAPHIC = NARR.get("_infographic", {})
DASHBOARD = NARR.get("_dashboard", {})
SECTION_VIZ = NARR.get("_section_viz", {})

FACTS = POOL["facts"]
LANG = cfg("lang", "ru")

CONTRADICTIONS = load_contradictions(TOPIC)
_STANDALONE_FIDS, _CONTRADICTION_GROUPS = partition_facts(FACTS, CONTRADICTIONS)

# source name+year comes from pool (inserted by enrich_sources.py); fallback — source_meta.json
SRC = load(ROOT / "source_meta.json", {})
for _f in FACTS:
    for _p in _f.get("provenance", []):
        if _p.get("source") and _p.get("source_name"):
            SRC.setdefault(_p["source"], {"name": _p["source_name"], "year": _p.get("source_year")})

# --- human-readable engine names ---
ENGINE = {
    "exa_research": "Exa research",
    "exa_answer": "Exa answer",
    "openai_deep": "OpenAI o4-mini DR",
    "perplexity_sonar": "Perplexity sonar",
    "perplexity_deep": "Perplexity deep",
    "claude_deepresearch": "Claude DR",
    "gemini": "Gemini",
    "re-search": "re-search OA",
}
CLASS_NAME = {"A": "primary source · science · gov", "B": "secondary", "C": "blog · vendor"}
CONF_EN = {"high": "high", "medium": "medium", "low": "low"}
CONF_DOT = {"high": "●●●", "medium": "●●○", "low": "●○○"}
CONF_ORDER = {"high": 0, "medium": 1, "low": 2}
# closed dictionary of rejection reasons (mono-tags in the "To review" block)
REASON = {"BROKEN_SOURCE": "link is dead or unauditable", "MISATTRIBUTED": "source is live but fact not found on it",
          "UNSOURCED": "engine provided no link"}

# section order: from config, otherwise — order of first appearance in data
_seen_order = []
for _f in FACTS:
    if _f["section"] not in _seen_order:
        _seen_order.append(_f["section"])
SECTION_ORDER = cfg("section_order") or _seen_order


def src_label(url):
    """Source caption: «Name (year)» or «Name» (for plain-text contexts)."""
    m = SRC.get(url)
    if not m:
        return domain(url)
    return f'{m["name"]} ({m["year"]})' if m.get("year") else m["name"]


def src_link(url, paren=True):
    """Academic citation: link on name only, year outside.
    paren=True → separate chip «<a>Name</a> (year)»; paren=False → inside parens «<a>Name</a>, year»."""
    m = SRC.get(url)
    name = m["name"] if m else domain(url)
    a = f'<a class="src" href="{esc(url)}" target="_blank" rel="noopener">{esc(name)}</a>'
    if m and m.get("year"):
        a += f' ({m["year"]})' if paren else f', {m["year"]}'
    return a


def engine_badges(prov):
    seen, out = set(), []
    for p in prov:
        e = p["engine"]
        if e in seen:
            continue
        seen.add(e)
        out.append(f'<span class="eng">{esc(ENGINE.get(e, e))}</span>')
    return "".join(out)


def source_links(prov, best):
    urls, out = [], []
    if best:
        urls.append(best)
    for p in prov:
        s = p.get("source")
        if s and s not in urls:
            urls.append(s)
    for u in urls[:3]:
        out.append(src_link(u))
    return out


def quote_block(quote, source):
    """Render a collapsible verbatim excerpt block. Returns empty string if quote is falsy."""
    if not quote:
        return ""
    link = src_link(source) if source else ""
    sep = " — " if link else ""
    return f'<details class="src-quote"><summary>what the source says</summary>«{esc(quote)}»{sep}{link}</details>'


def fact_block(f):
    cls = f.get("best_class") or "C"
    conf = f.get("confidence", "medium")
    review = ' data-review="1"' if f.get("needs_review") else ""
    note = f.get("note")
    note_html = f'<div class="note">{esc(note)}</div>' if note else ""
    corrected = (f.get("corrected") or "").strip()
    corrected_html = (f'<div class="corrected-badge">⚠ source says: «{esc(corrected)}»</div>'
                      if corrected else "")
    # Stale source badge: if year is present and older than stale_years threshold (default 3)
    stale_years = int(cfg("stale_years") or 3)
    best_year = f.get("best_source_year")
    stale_html = ""
    if best_year:
        try:
            if int(best_year) < (_CURRENT_YEAR - stale_years):
                stale_html = f'<div class="corrected-badge">⏳ source {best_year}</div>'
        except (ValueError, TypeError):
            pass
    quote = (f.get("quote") or "").strip()
    quote_html = quote_block(quote, f.get("best_source"))
    links = source_links(f.get("provenance", []), f.get("best_source"))
    return f"""<article class="fact"{review}>
  <p class="claim">{esc(f['text'])}</p>
  <div class="meta">
    <span class="cls cls-{cls}" title="{CLASS_NAME.get(cls,'')}">{cls}</span>
    <span class="conf" title="confidence {CONF_EN.get(conf,conf)}">{CONF_DOT.get(conf,'●●○')}</span>
    <span class="engs">{engine_badges(f.get('provenance', []))}</span>
    <span class="srcs">{''.join(links)}</span>
  </div>
  {corrected_html}
  {stale_html}
  {quote_html}
  {note_html}
</article>"""


def stance_chip(stance):
    """Render stance chip for contradiction group member."""
    if not stance:
        return ""
    STANCE_PROPS = {
        "поддерживает": ("st-pro", "▲ supports"),
        "опровергает": ("st-con", "▼ refutes"),
        "смешанно": ("st-mix", "◆ mixed"),
    }
    cls, label = STANCE_PROPS.get(stance, ("st-mix", f"◆ {esc(stance)}"))
    return f'<div class="stance-chip {cls}">{label}</div>'


def contradiction_block(grp, fid_to_fact):
    """Render a contradiction group: header + member fact cards side by side in a CSS grid."""
    issue = esc(grp.get("issue", "sources disagree"))
    note = grp.get("note", "")
    note_html = f'<div class="ct-note">{esc(note)}</div>' if note else ""
    stances = grp.get("stances", {})
    cards = ""
    for fid in grp["fids"]:
        chip = stance_chip(stances.get(fid))
        cards += chip + fact_block(fid_to_fact[fid])
    return f"""<div class="contradiction">
  <div class="ct-head">⚡ Sources disagree: {issue}</div>
  {note_html}
  <div class="ct-grid">
{cards}
  </div>
</div>"""


def keypoints_html(sec):
    pts = KEYPOINTS.get(sec)
    if not pts:
        return ""
    lis = "".join(f"<li>{esc(p)}</li>" for p in pts)
    return f'<ul class="keys">{lis}</ul>'


def table_html(sec):
    t = TABLES.get(sec)
    if not t:
        return ""
    head = "".join(f"<th>{esc(c)}</th>" for c in t.get("cols", []))
    body = ""
    for row in t.get("rows", []):
        body += "<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>"
    foot = f'<tfoot><tr><td colspan="{len(t.get("cols",[]))}">{esc(t["foot"])}</td></tr></tfoot>' if t.get("foot") else ""
    cap = f'<figcaption>{esc(t["title"])}</figcaption>' if t.get("title") else ""
    return (f'<figure class="tbl">{cap}<table><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody>{foot}</table></figure>')


def pick_tldr():
    out, by = [], {}
    for f in FACTS:
        by.setdefault(f["section"], []).append(f)
    for sec in SECTION_ORDER:
        items = by.get(sec, [])
        if not items:
            continue
        items = sorted(items, key=lambda f: (
            CONF_ORDER.get(f.get("confidence"), 3),
            0 if f.get("best_class") == "A" else 1,
            -f.get("engines_count", 0)))
        out.append(items[0])
    return out




def plural(n, one, few, many):
    n = abs(int(n)) % 100
    if 11 <= n <= 19: return many
    d = n % 10
    if d == 1: return one
    if 2 <= d <= 4: return few
    return many

def section_viz_html(sec):
    v = SECTION_VIZ.get(sec)
    builder = _VIZ.get(v.get("type")) if v else None
    if not builder:
        return ""
    cap = f'<figcaption>{esc(v["title"])}</figcaption>' if v.get("title") else ""
    note = f'<div class="svz-note">{esc(v["note"])}</div>' if v.get("note") else ""
    return f'<figure class="svz">{cap}{builder(v)}{note}</figure>'



# ---------- footnotes: inline prose links → superscript numbers (academic style) ----------
FOOTNOTES = []      # [(label, url)] global numbering across the document
_FN_INDEX = {}      # url -> number

_A_RE = re.compile(r"<a href='([^']+)'[^>]*>(.*?)</a>", re.S)

def _fn_num(url, label):
    n = _FN_INDEX.get(url)
    if n is None:
        n = len(FOOTNOTES) + 1
        _FN_INDEX[url] = n
        FOOTNOTES.append((re.sub(r"<[^>]+>", "", label).strip(), url))
    return n

def footnotize(html):
    """Replaces (…links…) in prose with superscript footnote numbers. Parens from links only."""
    def _paren(m):
        inner = m.group(1)
        links = _A_RE.findall(inner)
        rest = _A_RE.sub("", inner)
        if links and not re.search(r"[0-9A-Za-zА-Яа-яЁё]", rest):
            sups = ",".join(
                f'<a href="{u}" target="_blank" rel="noopener">{_fn_num(u, l)}</a>'
                for u, l in links)
            return f'<sup class="fnref">{sups}</sup>'
        return m.group(0)
    return re.sub(r"\s*\(([^()]*)\)", _paren, html)

def fnotes_block(start, end):
    if end <= start:
        return ""
    rows = "".join(
        f'<li value="{i+1}">{esc(lbl)} — <a href="{u}" target="_blank" rel="noopener">{esc(u)}</a></li>'
        for i, (lbl, u) in enumerate(FOOTNOTES[start:end], start))
    return f'<div class="fnotes"><span class="fn-lbl">Footnotes</span><ol>{rows}</ol></div>'


# ---------- body assembly ----------
by_sec = {}
for f in FACTS:
    by_sec.setdefault(f["section"], []).append(f)

# build lookup for contradiction rendering
_fid_to_fact = {f["fid"]: f for f in FACTS}

# contradiction groups keyed by section of their FIRST member fact
_ct_by_sec = {}
for _grp in _CONTRADICTION_GROUPS:
    _first_fid = _grp["fids"][0]
    _sec_key = _fid_to_fact[_first_fid]["section"]
    _ct_by_sec.setdefault(_sec_key, []).append(_grp)

sections_html = []
PROSE_WARN = []  # soft guard: sections where prose exceeds the limit (bullets should lead)
ordered = [s for s in SECTION_ORDER if s in by_sec] + [s for s in by_sec if s not in SECTION_ORDER]
for i, sec in enumerate(ordered, 1):
    items = sorted(by_sec[sec], key=lambda f: (
        CONF_ORDER.get(f.get("confidence"), 3),
        0 if f.get("best_class") == "A" else (1 if f.get("best_class") == "B" else 2),
        -f.get("engines_count", 0)))
    # class summary for evidence caption
    cc = {"A": 0, "B": 0, "C": 0}
    for f in items:
        cc[f.get("best_class", "C")] = cc.get(f.get("best_class", "C"), 0) + 1
    cls_summary = " ".join(f'{k} {cc[k]}' for k in ("A", "B", "C") if cc[k])
    # standalone facts: exclude any fid in a contradiction group
    standalone_items = [f for f in items if f["fid"] in _STANDALONE_FIDS]
    facts_html = "\n".join(fact_block(f) for f in standalone_items)
    # contradiction blocks for this section (keyed by first member's section)
    ct_blocks_html = "".join(
        contradiction_block(grp, _fid_to_fact)
        for grp in _ct_by_sec.get(sec, [])
    )
    narrative = NARR.get(sec, "")
    _fn_start = len(FOOTNOTES)
    narrative_fn = footnotize(narrative) if narrative else ""
    narr_html = f'<div class="narr">{narrative_fn}</div>' if narrative else ""
    # Soft prose guard (principle from report-craft: lead with bullets, prose is a short bridge).
    # Count sentences in plain text; >4 or >600 chars — warn, do not block.
    _ptext = re.sub(r"<[^>]+>", " ", narrative)
    # decimal points (7.55, p=0.38) — not sentence boundaries
    _nsent = len([s for s in re.split(r"(?<!\d)[.!?]+(?!\d)", _ptext) if s.strip()])
    if _nsent > 4 or len(_ptext) > 600:
        PROSE_WARN.append(f"  · «{sec}»: {_nsent} sentences, {len(_ptext)} chars (limit 4 / 600)")
    sw = SO_WHAT.get(sec, "")
    sw_html = (f'<aside class="sowhat"><div class="sw-lbl">So what</div>'
               f'<p>{esc(sw)}</p></aside>') if sw else ""
    fnotes_html = fnotes_block(_fn_start, len(FOOTNOTES))
    sections_html.append(f"""<section class="sec" id="sec-{i}">
  <div class="sec-head"><span class="sec-num">{i:02d}</span><h2>{esc(sec)}</h2><span class="sec-count">{len(items)} facts</span></div>
  {keypoints_html(sec)}
  {narr_html}
  {table_html(sec)}
  {section_viz_html(sec)}
  {sw_html}
  {fnotes_html}
  <details class="evidence">
    <summary>Evidence · {len(items)} · {cls_summary}</summary>
    {ct_blocks_html}
    {facts_html}
  </details>
</section>""")

# ---------- navigation: sidebar (HTML) + table-of-contents page (PDF) ----------
nav_items = [("00", cfg("tldr_title", "In brief"), "#tldr")]
nav_items += [(f"{i:02d}", sec, f"#sec-{i}") for i, sec in enumerate(ordered, 1)]
if ACTION_PLAN:
    nav_items.append(("→", "Action plan", "#plan"))
nav_items.append(("·", "Rejected claims", "#review"))

sidenav_html = ('<nav class="sidenav" aria-label="Sections"><div class="sn-lbl">Contents</div><ol>'
                + "".join(f'<li><a href="{h}"><span class="sn-n">{n}</span><span>{esc(t)}</span></a></li>'
                          for n, t, h in nav_items)
                + "</ol></nav>")

toc_html = ('<section class="toc-print"><div class="kicker">Contents</div>'
            '<ol>'
            + "".join(f'<li><a href="{h}"><span class="tp-n">{n}</span>'
                      f'<span class="tp-t">{esc(t)}</span></a></li>'
                      for n, t, h in nav_items)
            + "</ol></section>")

# ---------- In brief ----------
_tldr_override = NARR.get("_tldr")
if isinstance(_tldr_override, list) and _tldr_override:
    tldr_html = "\n".join(f'<li><span>{footnotize(t)}</span></li>' for t in _tldr_override)
else:
    tldr_items = pick_tldr()
    tldr_html = "\n".join(
        f'<li><span>{esc(f["text"])} ({src_link(f.get("best_source",""), paren=False)})</span></li>'
        for f in tldr_items if f.get("best_source"))

# ---------- To review ----------
rec_raw = REJ.get("recovery_candidates", [])
seen_txt, rec = {}, []
for r in sorted(rec_raw, key=lambda x: (0 if x.get("source_alive") else 1)):
    key = " ".join((r.get("text") or "").lower().split())[:120]
    if key in seen_txt:
        continue
    seen_txt[key] = True
    rec.append(r)
rec = sorted(rec, key=lambda x: (0 if x.get("source_alive") else 1))
rev_rows = []
for r in rec:
    src = r.get("source")
    why = r.get("judge_note") or r.get("fair_why") or ""
    eng = ENGINE.get(r.get("engine"), r.get("engine", ""))
    tag = REASON.get(r.get("label"), r.get("label", ""))
    link = (src_link(src) if src else '<span class="nolink">source not found</span>')
    rev_rows.append(f"""<article class="rfact">
  <p class="claim">{esc(r.get('text',''))}</p>
  <div class="meta">
    <span class="rlabel">{esc(tag)}</span>
    <span class="eng">{esc(eng)}</span>
    <span class="srcs">{link}</span>
  </div>
  {f'<div class="rwhy">{esc(why)}</div>' if why else ''}
</article>""")

summ = REJ.get("summary", {})
n_facts = len(FACTS)
n_rev = len(rec)
n_contradictions = len(_CONTRADICTION_GROUPS)
engines_used = sorted({ENGINE.get(p["engine"], p["engine"]) for f in FACTS for p in f["provenance"]})
today = datetime.date.today().isoformat()

# ---------- infographic: dashboard of topic target numbers (from narratives._infographic) ----------
infographic_html = ""
if INFOGRAPHIC.get("stats"):
    cards = "".join(
        f'<div class="stat"><span class="sv">{esc(s.get("value",""))}</span>'
        f'<span class="su">{esc(s.get("unit",""))}</span>'
        f'<span class="sl">{esc(s.get("label",""))}</span></div>'
        for s in INFOGRAPHIC["stats"])
    cap = f'<figcaption>{esc(INFOGRAPHIC["caption"])}</figcaption>' if INFOGRAPHIC.get("caption") else ""
    titl = f'<div class="ig-title">{esc(INFOGRAPHIC["title"])}</div>' if INFOGRAPHIC.get("title") else ""
    infographic_html = f'<figure class="infographic">{titl}<div class="statgrid">{cards}</div>{cap}</figure>'


# ---------- Editorial Warmth dashboard: hero (gauge + track) + zone strips ----------
def _zone_gradient(lo, hi, zones):
    """linear-gradient with hard stops: zones are coloured, gaps — var(--line)."""
    stops, cursor = [], lo
    for z in sorted(zones, key=lambda z: z[0]):
        a, b, kind = z[0], z[1], z[2]
        if a > cursor:
            stops.append((_pos(cursor, lo, hi), _pos(a, lo, hi), "var(--line)"))
        stops.append((_pos(a, lo, hi), _pos(b, lo, hi), _ZONE_BAND.get(kind, "var(--line)")))
        cursor = b
    if cursor < hi:
        stops.append((_pos(cursor, lo, hi), _pos(hi, lo, hi), "var(--line)"))
    segs = ", ".join(f"{c} {a:.1f}% {b:.1f}%" for a, b, c in stops)
    return f"linear-gradient(90deg, {segs})"


def _range_strip(r):
    lo, hi = r["min"], r["max"]
    grad = _zone_gradient(lo, hi, r.get("zones", []))
    mark = ""
    if "marker" in r:
        mark = f'<span class="strip-mark" style="left:{_pos(r["marker"], lo, hi):.1f}%"></span>'
    elif "marker_band" in r:
        a = _pos(r["marker_band"][0], lo, hi)
        b = _pos(r["marker_band"][1], lo, hi)
        mark = f'<span class="strip-mband" style="left:{a:.1f}%;right:{100 - b:.1f}%"></span>'
    note = f'<div class="strip-note">{esc(r["note"])}</div>' if r.get("note") else ""
    return (f'<div class="strip"><div class="strip-head">'
            f'<span class="strip-v">{esc(r["marker_label"])}</span>'
            f'<span class="strip-l">{esc(r["label"])} · {esc(r["unit"])}</span></div>'
            f'<div class="strip-bar-wrap"><div class="strip-bar" style="background:{grad}">{mark}</div>'
            f'<div class="strip-ax"><span>{_num(lo)}</span><span>{_num(hi)}</span></div>{note}</div></div>')


# ---------- dashboard hero: declarative widgets by type (topic-agnostic) ----------
_HERO_ZONE = {"risk": "var(--zr-b)", "warn": "var(--zw-b)", "good": "var(--zg)", "neutral": "var(--line)"}


def _hero_track(w):
    """Progress track: from → to on scale min..max. Generic (any path to a goal)."""
    lo, hi = w["min"], w["max"]
    now, goal = _pos(w["from"], lo, hi), _pos(w["to"], lo, hi)
    gl, gr = min(now, goal), max(now, goal)
    unit = esc(w.get("unit", ""))
    delta = w.get("delta_label")
    if delta is None:
        d = round(float(w["from"]) - float(w["to"]), 1)
        delta = f'−{_num(abs(d))} {unit}'.strip()
    delta_html = f'<span class="wdelta">{esc(delta)}</span>' if delta else ""
    meta = w.get("meta", "")  # raw text/HTML from config (can include <b>)
    meta_html = f'<div class="wmeta">{meta}</div>' if meta else ""
    from_lbl = esc(w.get("from_label", "now"))
    to_lbl = esc(w.get("to_label", "goal"))
    return (f'<div class="hcard">'
            f'<div class="hl">{esc(w["label"])}</div>'
            f'<div class="wtop"><span class="wnow">{_num(w["from"])}</span>'
            f'<span class="warr">→</span><span class="wgoal">{_num(w["to"])}</span>'
            f'<span class="wun">{unit}</span>{delta_html}</div>'
            f'<div class="wtrack">'
            f'<span class="gap" style="left:{gl:.1f}%;right:{100 - gr:.1f}%"></span>'
            f'<span class="goal" style="left:{goal:.1f}%"></span>'
            f'<span class="now" style="left:{now:.1f}%"></span></div>'
            f'<div class="wcap"><span class="c-goal" style="left:{goal:.1f}%">{to_lbl}</span>'
            f'<span class="c-now" style="left:{now:.1f}%">{from_lbl}</span></div>'
            f'<div class="wends"><span>{_num(lo)}</span><span>{_num(hi)}</span></div>'
            f'{meta_html}</div>')


def _hero_gauge(w):
    """Orientation gauge with three zones (risk/warn/good). Generic (readiness, index, score)."""
    zones = w.get("zones") or [[0, 33, "risk"], [33, 67, "warn"], [67, 100, "good"]]
    legs = ""
    for z in zones:
        a, b, kind = z[0], z[1], z[2]
        legs += (f'<span><i style="background:{_HERO_ZONE.get(kind, "var(--line)")}"></i>'
                 f'{_num(a)}–{_num(b)}</span>')
    sub = f'<span class="rt">{esc(w["sub"])}</span>' if w.get("sub") else ""
    return (f'<div class="hcard dial-wrap"><div class="hl">{esc(w["label"])}</div>'
            f'<div class="dial"><div class="read"><span class="rv">{esc(w["center"])}</span>'
            f'{sub}</div></div><div class="dial-zones">{legs}</div></div>')


def _hero_stat(w):
    """Number-reference card. Generic (any topic target numbers)."""
    cells = "".join(f'<div class="stat"><span class="sv">{esc(s.get("value",""))}</span>'
                    f'<span class="su">{esc(s.get("unit",""))}</span>'
                    f'<span class="sl">{esc(s.get("label",""))}</span></div>'
                    for s in w.get("items", []))
    lbl = f'<div class="hl">{esc(w["label"])}</div>' if w.get("label") else ""
    return f'<div class="hcard">{lbl}<div class="statgrid">{cells}</div></div>'


_HERO = {"track": _hero_track, "gauge": _hero_gauge, "stat": _hero_stat}


def _hero_list_from(dash):
    """Hero cards come from dash['hero'] (types: track / gauge / stat)."""
    return dash.get("hero", [])


def _funnel_block(fn):
    total, ok, rev = fn["total"], fn["confirmed"], fn["review"]
    okp = ok / total * 100 if total else 0
    return (f'<div class="funnel"><div class="funnel-l">Fact-check funnel</div>'
            f'<div class="funnel-bar"><span class="f-ok" style="flex:{ok}"></span>'
            f'<span class="f-rev" style="flex:{rev}"></span></div>'
            f'<div class="funnel-leg"><span class="t"><b>{ok}</b> confirmed</span>'
            f'<span><b>{rev}</b> to review</span>'
            f'<span>{okp:.0f}% survived out of {total}</span></div></div>')


dashboard_html = ""
if DASHBOARD:
    _title = (f'<div class="dash-title">{esc(DASHBOARD.get("title", ""))}'
              f'<em>{len(DASHBOARD.get("ranges", [])) + 2} reference points</em></div>'
              if DASHBOARD.get("title") else "")
    _hero = "".join(_HERO[h["type"]](h) for h in _hero_list_from(DASHBOARD) if h.get("type") in _HERO)
    _hero = f'<div class="hero">{_hero}</div>' if _hero else ""
    _strips = "".join(_range_strip(r) for r in DASHBOARD.get("ranges", []))
    _strips = f'<div class="strips">{_strips}</div>' if _strips else ""
    _funnel = _funnel_block(DASHBOARD["funnel"]) if DASHBOARD.get("funnel") else ""
    _dcap = f'<p class="dash-cap">{esc(DASHBOARD["caption"])}</p>' if DASHBOARD.get("caption") else ""
    dashboard_html = f'<section class="dash">{_title}{_hero}{_strips}{_funnel}{_dcap}</section>'



# ---------- final action plan (so what per item) ----------
ap_rows = "".join(
    f'<li><span class="ap-sec">{esc(sec)}</span><span class="ap-act">{esc(act)}</span></li>'
    for sec, act in ACTION_PLAN)
actionplan_html = f"""<section class="plan" id="plan">
  <div class="sec-head"><span class="sec-num">→</span><h2>Action plan</h2><span class="sec-count">so what per item</span></div>
  <ol class="ap">{ap_rows}</ol>
</section>""" if ACTION_PLAN else ""

# report subtitle — only if set in topic config (off by default)
personal_dek = cfg("personal_dek", "") if cfg("show_personal_dek") else ""

page_title = cfg("page_title") or POOL.get("topic", TOPIC)
title_html = cfg("title_html") or esc(POOL.get("topic", TOPIC))
intro_html = cfg("intro")
footer_methods = cfg("footer_methods") or "Sources found by deep-search engines; for each fact you can see which engines and how many."
_stale_years_val = int(cfg("stale_years") or 3)
footer_methods = footer_methods + f" Recency: ⏳ next to a fact means the source is older than {_stale_years_val} years."
footer_note = cfg("footer_note")

# ---------- HTML ----------
OUT = f"""<!doctype html>
<html lang="{esc(LANG)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(page_title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Commissioner:wght@400;500;600;700;800;900&family=Onest:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Caveat:wght@500;600;700&display=swap" rel="stylesheet">
<style>
""" + STYLE_CSS + f"""
</style>
</head>
<body>
{sidenav_html}
<div class="wrap">

  <p class="kicker">{esc(cfg('kicker', 'Verified report · fact-check funnel'))}</p>
  <h1>{title_html}</h1>
  {f'<p class="dek">{esc(cfg("dek"))}</p>' if cfg("dek") else ''}
  {f'<p class="dek personal">{esc(personal_dek)}</p>' if personal_dek else ''}
  <div class="byline">
    <span><b>{n_facts}</b> verified {('fact' if n_facts == 1 else 'facts')}</span>
    <span><b>{len(engines_used)}</b> engines</span>
    {f'<span>⚡ <b>{n_contradictions}</b> source disagreements</span>' if n_contradictions else ""}
    <span>{today}</span>
  </div>

  {f'<p class="intro">{intro_html}</p>' if intro_html else ''}

  {dashboard_html or infographic_html}

  {toc_html}

  <div class="tldr" id="tldr">
    <span class="lbl">In brief</span>
    <h3>{esc(cfg('tldr_title', 'If you read only this'))}</h3>
    <ol>
{tldr_html}
    </ol>
  </div>

{''.join(sections_html)}

  {actionplan_html}

  <details class="review" id="review" open>
    <summary><span class="rsum-h2">Rejected claims</span><span class="rsum-n">{n_rev} {('claim' if n_rev == 1 else 'claims')} · did not pass fact-check, reason shown for each</span></summary>
    <p class="sub">These claims were set aside by the funnel: the source turned out to be broken, off-topic, or missing. Each has a candidate source — open and decide for yourself. Out of {summ.get('total_rejected','—')} rejected, after deduplication {n_rev} remain with a candidate (live sources first).</p>
{''.join(rev_rows)}
  </details>

  <div class="foot">
    <p><b>How to read.</b> Source class and confidence are shown next to each fact.</p>
    <div class="legend">
      <span><span class="cls cls-A">A</span> primary source · science · gov</span>
      <span><span class="cls cls-B">B</span> secondary</span>
      <span><span class="cls cls-C">C</span> blog · vendor</span>
      <span><span class="conf">●●●</span> confidence</span>
    </div>
    <p>{esc(footer_methods)}</p>
    {f'<p>{esc(footer_note)}</p>' if footer_note else ''}
  </div>

</div>
</body>
</html>"""

(ROOT / "reports").mkdir(exist_ok=True)
dst = ROOT / (cfg("out") or f"reports/REPORT-{TOPIC}.html")
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(OUT, encoding="utf-8")
print(f"done: {dst} ({len(OUT)//1024} KB, {n_facts} facts, {n_rev} to review, {len(engines_used)} engines)")
if PROSE_WARN:
    print(f"⚠ prose exceeds limit in {len(PROSE_WARN)} sections (lead with bullets, prose is a bridge ≤4 sentences):")
    print("\n".join(PROSE_WARN))
