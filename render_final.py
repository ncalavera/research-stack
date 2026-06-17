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


def esc(t):
    return html.escape(str(t))


def domain(url):
    try:
        return url.split("/")[2].replace("www.", "")
    except Exception:
        return url


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

# ---------- shared scale helpers (used by both sections and dashboard) ----------
def _num(x):
    """Number without trailing .0 for labels."""
    try:
        f = float(x)
        return str(int(f)) if f == int(f) else str(x)
    except (TypeError, ValueError):
        return str(x)


def _pos(v, lo, hi):
    """Position of value v on scale lo..hi in percent (0..100)."""
    if hi == lo:
        return 0.0
    return max(0.0, min(100.0, (float(v) - lo) / (hi - lo) * 100))


_ZONE_BAND = {"good": "var(--zg-b)", "warn": "var(--zw-b)", "risk": "var(--zr-b)",
              "neutral": "var(--line)"}


# ---------- mini-charts inside sections (narratives._section_viz) ----------
def _viz_stacked(v):
    total = sum(float(s["value"]) for s in v["segments"]) or 1
    bar, leg = "", ""
    for s in v["segments"]:
        w = float(s["value"]) / total * 100
        c = _ZONE_BAND.get(s.get("kind"), "var(--line)")
        bar += f'<span style="width:{w:.1f}%;background:{c}"></span>'
        sub = f' {esc(s["sub"])}' if s.get("sub") else ""
        leg += f'<span><i style="background:{c}"></i><b>{esc(s["label"])}</b>{sub}</span>'
    return f'<div class="stk-bar">{bar}</div><div class="stk-leg">{leg}</div>'


def _viz_dots(v):
    lo, hi = v["good"]
    cells = "".join(
        '<i class="in"></i>' if lo <= i <= hi else "<i></i>"
        for i in range(1, int(v["total"]) + 1))
    return f'<div class="dots">{cells}</div>'


def _viz_timeline(v):
    ds, de = v["day_start"], v["day_end"]
    w0, w1 = v["window"]
    win = (f'<span class="tl-win" style="left:{_pos(w0, ds, de):.1f}%;'
           f'right:{100 - _pos(w1, ds, de):.1f}%"></span>')
    doses = "".join(
        f'<span class="tl-dose" style="left:{_pos(d["at"], ds, de):.1f}%"><b>{d["g"]}g</b></span>'
        for d in v.get("doses", []))
    hrs = "".join(f"<span>{int(h):02d}:00</span>"
                  for h in (ds, ds + (de - ds) / 3, ds + 2 * (de - ds) / 3, de))
    return f'<div class="tl-bar">{win}{doses}</div><div class="tl-hours">{hrs}</div>'


def _viz_bands(v):
    lo, hi = v["min"], v["max"]
    segs = ""
    for b in v["bands"]:
        a = _pos(b["lo"], lo, hi)
        z = _pos(b["hi"], lo, hi)
        c = _ZONE_BAND.get(b.get("kind"), "var(--line)")
        segs += (f'<span class="bd-seg" style="left:{a:.1f}%;right:{100 - z:.1f}%;'
                 f'background:{c}"><em>{esc(b["label"])}</em></span>')
    tgt = ""
    if v.get("target"):
        a = _pos(v["target"][0], lo, hi)
        z = _pos(v["target"][1], lo, hi)
        tgt = f'<span class="bd-target" style="left:{a:.1f}%;right:{100 - z:.1f}%"></span>'
    u = esc(v.get("unit", ""))
    return (f'<div class="bd-bar">{segs}{tgt}</div>'
            f'<div class="bd-ax"><span>{_num(lo)}{u}</span><span>{_num(hi)}{u}</span></div>')


def _viz_bars(v):
    """Category comparison: horizontal bars from zero, value labelled directly next to bar
    (direct labeling, no legend). For "compare/rank" questions, not for parts of a whole."""
    rows = v["bars"]
    mx = max((float(b["value"]) for b in rows), default=1) or 1
    u = esc(v.get("unit", ""))
    out = ""
    for b in rows:
        w = float(b["value"]) / mx * 100
        c = _ZONE_BAND.get(b.get("kind"), "var(--ink)")
        out += (f'<div class="br-row"><span class="br-lbl">{esc(b["label"])}</span>'
                f'<span class="br-track"><span class="br-fill" style="width:{w:.1f}%;background:{c}"></span></span>'
                f'<span class="br-val">{_num(b["value"])}{u}</span></div>')
    return f'<div class="br">{out}</div>'


def _viz_line(v):
    """Time trend: polyline through points (SVG), zero baseline by default.
    For "how it changed" questions, not for comparing unrelated categories."""
    pts = v["points"]  # [{x: label, y: number}]
    ys = [float(p["y"]) for p in pts]
    lo = v.get("min", 0)
    hi = v.get("max", max(ys) if ys else 1)
    rng = (hi - lo) or 1
    n = len(pts)
    W, H = 100.0, 42.0
    def sx(i): return (i / (n - 1) * W) if n > 1 else 0
    def sy(y): return H - (float(y) - lo) / rng * H
    poly = " ".join(f"{sx(i):.1f},{sy(p['y']):.1f}" for i, p in enumerate(pts))
    dots = "".join(f'<circle cx="{sx(i):.1f}" cy="{sy(p["y"]):.1f}" r="1.6" fill="var(--ink)"/>'
                   for i, p in enumerate(pts))
    xlabels = "".join(f"<span>{esc(str(p['x']))}</span>" for p in pts)
    u = esc(v.get("unit", ""))
    return (f'<div class="ln"><svg viewBox="0 0 {W:.0f} {H:.0f}" preserveAspectRatio="none" class="ln-svg">'
            f'<polyline points="{poly}" fill="none" stroke="var(--ink)" stroke-width="1.2" '
            f'vector-effect="non-scaling-stroke"/>{dots}</svg>'
            f'<div class="ln-ax">{xlabels}</div>'
            f'<div class="ln-ends"><span>{_num(lo)}{u}</span><span>{_num(hi)}{u}</span></div></div>')


def _viz_donut(v):
    """Part-of-whole as a ring (≤5 segments). Direct labels with percentage alongside, not a legend.
    Principle from report-craft: pie/donut — only for parts of a whole and ≤5 categories."""
    segs = v["segments"]
    total = sum(float(s["value"]) for s in segs) or 1
    R, C = 16.0, 2 * 3.14159265 * 16.0  # radius and circumference
    off, arcs, leg = 0.0, "", ""
    for s in segs:
        frac = float(s["value"]) / total
        c = _ZONE_BAND.get(s.get("kind"), "var(--ink)")
        dash = frac * C
        arcs += (f'<circle cx="21" cy="21" r="16" fill="none" stroke="{c}" stroke-width="8" '
                 f'stroke-dasharray="{dash:.2f} {C - dash:.2f}" stroke-dashoffset="{-off:.2f}" '
                 f'transform="rotate(-90 21 21)"/>')
        off += dash
        pct = round(frac * 100)
        leg += (f'<span><i style="background:{c}"></i><b>{esc(s["label"])}</b> {pct}%</span>')
    return (f'<div class="dn"><svg viewBox="0 0 42 42" class="dn-svg">{arcs}</svg>'
            f'<div class="dn-leg">{leg}</div></div>')


_VIZ = {"stacked": _viz_stacked, "dots": _viz_dots, "timeline": _viz_timeline,
        "bands": _viz_bands, "bars": _viz_bars, "line": _viz_line, "donut": _viz_donut}


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
:root{{
  --paper:#f8f6f1; --card:#fdfcf9; --ink:#1a1816; --soft:#6b6560; --fg3:#767069;
  --line:#e8e3d8; --rule:#d8d6d2;
  /* Editorial Warmth — accents are semantic: clay="progress", teal="confirmed", zones=risk/norm/goal */
  --clay:#b4532a; --clay-deep:#8a3d1e; --clay-tint:#f0ddd0;
  --teal:#1f5c5a; --teal-tint:#d7e5e2;
  --zg:#4c7a52; --zg-b:#c3d6bb;   /* good — line / band */
  --zw:#a9781f; --zw-b:#ecd6a4;   /* caution */
  --zr:#8c3b36; --zr-b:#ddb4ad;   /* risk */
  --disp:"Commissioner",system-ui,sans-serif;
  --body:"Onest",system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,monospace;
  --hand:"Caveat","Onest",cursive;
}}
@media(prefers-color-scheme:dark){{
  :root{{
    --paper:#1a1816; --card:#221e19; --ink:#ece7dd; --soft:#a39c8e; --fg3:#9a9286;
    --line:#2c2820; --rule:#3a352c;
    --clay:#e08a5c; --clay-deep:#e8a079; --clay-tint:#2e211a;
    --teal:#5fa8a2; --teal-tint:#16302e;
    --zg:#7fb07f; --zg-b:#33452f;
    --zw:#d6a84e; --zw-b:#463a1e;
    --zr:#d97169; --zr-b:#4a2925;
  }}
}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%;scroll-behavior:smooth}}
body{{margin:0;background:var(--paper);color:var(--ink);
  font:400 15px/1.56 var(--body);
  font-feature-settings:"ss01";-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
.wrap{{max-width:820px;margin:0 auto;padding:clamp(32px,5vw,56px) 28px 80px}}
::selection{{background:var(--ink);color:var(--paper)}}
a{{color:inherit}}
*{{scroll-margin-top:24px}}

/* ---- sidebar navigation (wide screen only, no JS) ---- */
.sidenav{{display:none}}
@media(min-width:1280px){{
  .sidenav{{display:block;position:fixed;top:56px;left:max(20px,calc(50% - 620px));width:186px;
    max-height:calc(100vh - 96px);overflow:auto}}
  .sidenav .sn-lbl{{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;
    color:var(--soft);margin:0 0 12px}}
  .sidenav ol{{list-style:none;margin:0;padding:0}}
  .sidenav li a{{display:flex;gap:9px;align-items:baseline;padding:5px 0;
    font:500 13px/1.32 var(--body);color:var(--soft);text-decoration:none;transition:color .12s}}
  .sidenav li a:hover{{color:var(--ink)}}
  .sidenav .sn-n{{font:600 11px/1.4 var(--mono);color:var(--fg3);min-width:18px;flex:none}}
}}

/* ---- table of contents page (print/PDF only) ---- */
.toc-print{{display:none}}

/* Typographic scale — 6 steps across the page: 11 / 13 / 15 / 19 / 24 / 40.
   11 — small detail (mono labels, badges, axes, table headers); 13 — numbers/values;
   15 — body text and bullets; 19 — dek and large scale numbers; 24 — H2; 40 — H1. */

/* ---- masthead ---- */
.kicker{{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);margin:0 0 20px}}
h1{{font:800 clamp(24px,7vw,40px)/0.98 var(--disp);letter-spacing:-.035em;margin:0 0 14px}}
.dek{{font:400 19px/1.34 var(--body);color:var(--soft);margin:0 0 4px;max-width:34ch;letter-spacing:-.01em}}
.dek.personal{{color:var(--ink);font-size:15px;line-height:1.5;max-width:54ch;margin-top:16px}}
.byline{{font:500 11px/1.5 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--soft);
  border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:15px 0;margin:30px 0 0;
  display:flex;flex-wrap:wrap;gap:8px 36px;font-variant-numeric:tabular-nums}}
.byline b{{color:var(--ink);font-weight:600;font-size:13px}}

/* ---- intro + single drop cap ---- */
.intro{{font-size:15px;line-height:1.54;margin:32px 0 8px;max-width:68ch}}
.intro::first-letter{{font:800 4.1em/.72 var(--disp);float:left;color:var(--ink);margin:9px 12px 0 0}}

/* ---- In brief — numbered register ---- */
.tldr{{margin:30px 0 10px;border-top:2px solid var(--ink);padding-top:4px}}
.tldr .lbl{{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);display:block;margin:14px 0 2px}}
.tldr h3{{font:700 24px/1.1 var(--disp);letter-spacing:-.025em;margin:2px 0 10px}}
.tldr ol{{margin:0;padding:0;list-style:none;counter-reset:tl}}
.tldr li{{display:grid;grid-template-columns:26px 1fr;gap:5px 12px;align-items:baseline;
  padding:10px 0;border-top:1px solid var(--line);counter-increment:tl}}
.tldr li:first-child{{border-top:0}}
.tldr li::before{{content:counter(tl,decimal-leading-zero);font:600 11px/1.7 var(--mono);color:var(--fg3)}}
.tldr li span{{font-size:15px;line-height:1.42}}

/* ---- sections ---- */
.sec{{margin:52px 0 0}}
.sec-head{{display:flex;align-items:baseline;gap:12px;border-bottom:1px solid var(--rule);padding-bottom:10px;margin-bottom:16px}}
.sec-num{{font:500 11px/1 var(--mono);color:var(--fg3)}}
.sec-head h2{{font:700 clamp(19px,3.6vw,24px)/1.06 var(--disp);letter-spacing:-.03em;margin:0;flex:1}}
.sec-count{{font:500 11px/1 var(--mono);color:var(--fg3);text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}}

/* ---- narrative ---- */
.narr{{font-size:15px;line-height:1.56;max-width:68ch;margin:0 0 4px}}
.narr p{{margin:0 0 13px}}
.narr a{{color:var(--teal);text-decoration:underline;text-decoration-color:var(--teal);text-underline-offset:3px;text-decoration-thickness:1px;transition:text-decoration-thickness .15s}}
.narr a:hover{{text-decoration-thickness:2px}}

/* ---- so what — marginalia ---- */
.sowhat{{margin:20px 0 6px;padding:0 0 2px 20px;border-left:2px solid var(--ink);max-width:62ch}}
.sw-lbl{{font:700 24px/1 var(--hand);color:var(--soft);display:inline-block;transform:rotate(-2.5deg);margin:0 0 3px}}
.sowhat p{{margin:0;font:500 15px/1.5 var(--body);color:var(--ink)}}

/* ---- key bullets ---- */
.keys{{max-width:68ch;margin:15px 0 4px;padding:0;list-style:none}}
.keys li{{position:relative;padding:6px 0 6px 20px;font-size:15px;line-height:1.5;border-bottom:1px solid var(--line)}}
.keys li:last-child{{border-bottom:0}}
.keys li::before{{content:"";position:absolute;left:2px;top:13px;width:5px;height:5px;background:var(--ink)}}

/* ---- table ---- */
.tbl{{margin:22px 0 6px;max-width:760px}}
.tbl figcaption{{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--soft);margin:0 0 10px}}
.tbl table{{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}}
.tbl th{{text-align:left;font:600 11px/1.3 var(--mono);letter-spacing:.05em;text-transform:uppercase;
  color:var(--soft);padding:0 14px 8px 0;border-bottom:1.5px solid var(--ink);vertical-align:bottom}}
.tbl td{{padding:9px 14px 9px 0;border-bottom:1px solid var(--line);vertical-align:top;line-height:1.4}}
.tbl td:first-child{{font-weight:600;color:var(--ink);white-space:nowrap}}
.tbl tbody tr:last-child td{{border-bottom:1.5px solid var(--rule)}}
.tbl tfoot td{{font:500 13px/1.4 var(--body);font-style:italic;color:var(--soft);
  padding-top:10px;border:0}}

/* ---- dashboard (Editorial Warmth): hero + zone strips ---- */
.dash{{margin:34px 0 8px}}
.dash-title{{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);
  margin:0 0 16px;display:flex;justify-content:space-between;align-items:baseline;gap:12px}}
.dash-title em{{font-style:normal;color:var(--fg3)}}

/* hero: gauge + track */
.hero{{display:flex;flex-wrap:wrap;gap:18px;margin:0 0 6px}}
.hero>.hcard{{flex:1 1 320px}}
.hero>.dial-wrap{{flex:0 0 204px}}
.hcard{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;
  box-shadow:0 1px 3px rgba(26,24,22,.05)}}
.hcard .hl{{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--soft);margin:0 0 14px}}
/* ---- number cards (top infographic + stat-hero dashboard) ---- */
.infographic{{margin:30px 0 8px}}
.ig-title{{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);margin:0 0 16px}}
.infographic figcaption{{margin:14px 0 0;font:400 13px/1.5 var(--body);color:var(--fg3);max-width:62ch}}
.statgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}}
.infographic>.statgrid .stat{{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:18px 18px 16px;box-shadow:0 1px 3px rgba(26,24,22,.05)}}
.stat{{display:flex;flex-direction:column;gap:3px}}
.stat .sv{{font:700 30px/1 var(--disp);letter-spacing:-.02em;color:var(--ink)}}
.stat .su{{font:600 11px/1.2 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--fg3)}}
.stat .sl{{margin-top:6px;font:400 13px/1.4 var(--body);color:var(--soft)}}

/* gauge (zone reference, no invented needle) */
.dial-wrap{{display:flex;flex-direction:column;align-items:center}}
.dial{{position:relative;width:150px;aspect-ratio:1;border-radius:50%;margin:2px 0 14px;
  background:conic-gradient(from 135deg,
    var(--zr-b) 0deg 89deg, var(--zw-b) 89deg 181deg, var(--zg) 181deg 270deg, transparent 270deg 360deg)}}
.dial::after{{content:"";position:absolute;inset:19px;border-radius:50%;background:var(--card);box-shadow:inset 0 0 0 1px var(--line)}}
.dial .read{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:2}}
.dial .rv{{font:800 24px/1 var(--disp);letter-spacing:-.03em;color:var(--zg)}}
.dial .rt{{font:600 11px/1.3 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--soft);margin-top:5px}}
.dial-zones{{display:flex;gap:11px;font:500 11px/1 var(--mono);letter-spacing:.02em}}
.dial-zones span{{display:inline-flex;align-items:center;gap:4px;color:var(--fg3)}}
.dial-zones i{{width:8px;height:8px;border-radius:2px}}

/* progress track: from → to */
.wtop{{display:flex;align-items:baseline;gap:8px;margin:0 0 22px}}
.wtop .wnow{{font:800 clamp(24px,5vw,40px)/.9 var(--disp);letter-spacing:-.035em;color:var(--clay);font-variant-numeric:tabular-nums}}
.wtop .warr{{font:600 19px/1 var(--mono);color:var(--fg3)}}
.wtop .wgoal{{font:800 24px/.9 var(--disp);letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}}
.wtop .wun{{font:600 13px/1 var(--mono);color:var(--soft);align-self:center}}
.wtop .wdelta{{margin-left:auto;align-self:center;font:600 11px/1 var(--mono);color:var(--clay-deep);
  border:1px solid var(--clay);border-radius:4px;padding:4px 8px}}
.wtrack{{position:relative;height:8px;border-radius:5px;background:var(--line)}}
.wtrack .gap{{position:absolute;top:0;bottom:0;border-radius:5px;
  background:repeating-linear-gradient(90deg,var(--clay-tint) 0 6px,transparent 6px 10px);box-shadow:inset 0 0 0 1px var(--clay-tint)}}
.wtrack .goal{{position:absolute;top:-7px;width:2px;height:22px;background:var(--ink)}}
.wtrack .now{{position:absolute;top:50%;width:14px;height:14px;border-radius:50%;background:var(--clay);
  transform:translate(-50%,-50%);box-shadow:0 0 0 3px var(--card)}}
.wcap{{position:relative;height:14px;margin-top:11px}}
.wcap span{{position:absolute;transform:translateX(-50%);font:600 11px/1 var(--mono);letter-spacing:.04em;
  text-transform:uppercase;white-space:nowrap}}
.wcap .c-now{{color:var(--clay-deep)}} .wcap .c-goal{{color:var(--ink)}}
.wends{{display:flex;justify-content:space-between;font:500 11px/1 var(--mono);color:var(--fg3);margin-top:7px}}
.wmeta{{margin:15px 0 0;padding-top:13px;border-top:1px solid var(--line);font:400 13px/1.5 var(--body);color:var(--soft)}}
.wmeta b{{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}}

/* zone strips per metric */
.strips{{margin:14px 0 0;border-top:1px solid var(--rule)}}
.strip{{display:grid;grid-template-columns:124px 1fr;gap:18px;align-items:center;
  padding:15px 0;border-bottom:1px solid var(--line)}}
.strip:last-child{{border-bottom:0}}
.strip-v{{font:800 19px/1 var(--disp);letter-spacing:-.02em;color:var(--ink);font-variant-numeric:tabular-nums}}
.strip-l{{display:block;font:600 11px/1.3 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--soft);margin-top:4px}}
.strip-bar{{position:relative;height:9px;border-radius:5px}}
.strip-mark{{position:absolute;top:-3px;height:15px;width:2px;background:var(--clay);border-radius:1px}}
.strip-mark::after{{content:"";position:absolute;top:-4px;left:-3px;width:8px;height:8px;border-radius:50%;background:var(--clay)}}
.strip-mband{{position:absolute;top:-2px;bottom:-2px;border:1.5px solid var(--clay);border-radius:4px}}
.strip-ax{{display:flex;justify-content:space-between;font:500 11px/1 var(--mono);color:var(--fg3);margin-top:6px}}
.strip-note{{font:400 13px/1.4 var(--body);font-style:italic;color:var(--fg3);margin-top:4px}}

/* fact-check funnel — proportional bar */
.funnel{{margin:18px 0 0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px 15px}}
.funnel-l{{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--soft);margin:0 0 11px}}
.funnel-bar{{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--line)}}
.funnel-bar .f-ok{{background:var(--teal)}} .funnel-bar .f-rev{{background:var(--rule)}}
.funnel-leg{{display:flex;justify-content:space-between;gap:10px;margin-top:10px;
  font:500 11px/1.4 var(--mono);color:var(--soft);flex-wrap:wrap}}
.funnel-leg b{{color:var(--ink)}} .funnel-leg .t b{{color:var(--teal)}}
.dash-cap{{margin:17px 0 0;font:400 13px/1.5 var(--body);color:var(--fg3);max-width:62ch}}
@media(max-width:560px){{
  .hero{{grid-template-columns:1fr}}
  .strip{{grid-template-columns:100px 1fr;gap:13px}}
}}

/* ---- mini-charts in sections ---- */
.svz{{margin:22px 0 6px;max-width:760px}}
.svz figcaption{{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--soft);margin:0 0 12px}}
.svz-note{{margin:11px 0 0;font:400 13px/1.45 var(--body);font-style:italic;color:var(--fg3)}}
/* sleep phase stack */
.stk-bar{{display:flex;height:34px;border-radius:7px;overflow:hidden;border:1px solid var(--line)}}
.stk-bar span{{display:block;min-width:2px}}
.stk-leg{{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:11px;font:500 11px/1.4 var(--mono);color:var(--soft)}}
.stk-leg span{{display:inline-flex;align-items:center;gap:6px}}
.stk-leg i{{width:9px;height:9px;border-radius:2px}}
.stk-leg b{{color:var(--ink);font-weight:600}}
/* training volume dot grid */
.dots{{display:flex;flex-wrap:wrap;gap:5px}}
.dots i{{width:15px;height:15px;border-radius:3px;border:1px solid var(--rule)}}
.dots i.in{{background:var(--zg);border-color:var(--zg)}}
/* daily protein timeline */
.tl-bar{{position:relative;height:38px;background:var(--card);border:1px solid var(--line);border-radius:8px}}
.tl-win{{position:absolute;top:5px;bottom:5px;border-radius:5px;background:var(--clay-tint);border:1px dashed var(--clay)}}
.tl-dose{{position:absolute;top:7px;bottom:7px;width:34px;transform:translateX(-50%);border-radius:4px;
  background:var(--zg);display:flex;align-items:center;justify-content:center}}
.tl-dose b{{font:700 11px/1 var(--mono);color:var(--paper)}}
.tl-hours{{display:flex;justify-content:space-between;margin-top:7px;font:500 11px/1 var(--mono);color:var(--fg3)}}
/* category bands (body fat %) */
.bd-bar{{position:relative;height:30px;border-radius:7px;background:var(--line)}}
.bd-seg{{position:absolute;top:0;bottom:0;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.bd-seg em{{font:600 11px/1 var(--mono);font-style:normal;letter-spacing:.04em;text-transform:uppercase;
  color:var(--ink);opacity:.7;padding:0 4px;white-space:nowrap}}
.bd-target{{position:absolute;top:-4px;bottom:-4px;border:2px solid var(--clay);border-radius:6px;pointer-events:none}}
.bd-ax{{display:flex;justify-content:space-between;margin-top:7px;font:500 11px/1 var(--mono);color:var(--fg3)}}

/* comparison bars (direct labeling, zero baseline) */
.br{{display:flex;flex-direction:column;gap:9px}}
.br-row{{display:grid;grid-template-columns:minmax(90px,30%) 1fr auto;align-items:center;gap:12px}}
.br-lbl{{font:500 13px/1.3 var(--body);color:var(--soft);text-align:right}}
.br-track{{height:18px;background:var(--line);border-radius:4px;overflow:hidden}}
.br-fill{{display:block;height:100%;border-radius:4px}}
.br-val{{font:600 13px/1 var(--mono);color:var(--ink);min-width:34px}}
/* part-of-whole ring */
.dn{{display:flex;align-items:center;gap:22px;flex-wrap:wrap}}
.dn-svg{{width:96px;height:96px;flex:none}}
.dn-leg{{display:flex;flex-direction:column;gap:8px;font:500 13px/1.3 var(--body);color:var(--soft)}}
.dn-leg span{{display:inline-flex;align-items:center;gap:8px}}
.dn-leg i{{width:11px;height:11px;border-radius:3px;flex:none}}
.dn-leg b{{color:var(--ink);font-weight:600}}
/* trend line */
.ln-svg{{width:100%;height:90px;display:block;overflow:visible}}
.ln-ax{{display:flex;justify-content:space-between;margin-top:7px;font:500 11px/1 var(--mono);color:var(--fg3)}}
.ln-ends{{display:flex;justify-content:space-between;margin-top:3px;font:500 10px/1 var(--mono);color:var(--fg3);opacity:.7}}

/* ---- action plan ---- */
.plan{{margin:56px 0 0}}
.plan .ap{{margin:8px 0 0;padding:0;list-style:none}}
.plan .ap li{{display:grid;grid-template-columns:22px 1fr;gap:2px 12px;
  padding:11px 0;border-bottom:1px solid var(--line)}}
.plan .ap li::before{{content:"☐";grid-column:1;grid-row:1/3;font:400 15px/1.3 var(--mono);color:var(--soft)}}
.ap-sec{{grid-column:2;font:600 11px/1.4 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--fg3)}}
.ap-act{{grid-column:2;font:500 15px/1.45 var(--body);color:var(--ink)}}

/* ---- evidence (collapsed) ---- */
.evidence{{margin:16px 0 0;max-width:62ch}}
.evidence>summary{{list-style:none;cursor:pointer;font:600 11px/1 var(--mono);letter-spacing:.08em;
  text-transform:uppercase;color:var(--soft);padding:11px 0;border-top:1px solid var(--line);
  display:flex;align-items:center;gap:8px;font-variant-numeric:tabular-nums}}
.evidence>summary::-webkit-details-marker{{display:none}}
.evidence>summary::before{{content:"+";font:500 13px/1 var(--mono);width:10px}}
.evidence[open]>summary::before{{content:"–"}}

/* ---- fact ---- */
.fact{{padding:13px 0;border-bottom:1px solid var(--line)}}
.claim{{margin:0 0 8px;font:400 15px/1.5 var(--body)}}
.meta{{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font:500 11px/1 var(--mono);color:var(--soft)}}
.cls{{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 4px;
  border-radius:4px;font:600 11px/1 var(--mono);border:1.5px solid var(--ink);color:var(--ink)}}
.cls-A{{background:var(--ink);color:var(--paper)}}
.cls-B{{background:var(--soft);color:var(--paper);border-color:var(--soft)}}
.cls-C{{background:transparent;color:var(--soft);border-color:var(--rule)}}
.conf{{letter-spacing:.06em;color:var(--ink);font-size:11px}}
.engs{{display:inline-flex;flex-wrap:wrap;gap:5px}}
.eng{{color:var(--fg3);border:1px solid var(--line);border-radius:4px;padding:2px 7px;font:500 11px/1 var(--mono)}}
.srcs{{display:inline-flex;flex-wrap:wrap;gap:4px 12px;margin-left:auto}}
.src{{color:var(--teal);text-decoration:underline;text-decoration-color:var(--teal);
  text-decoration-thickness:1px;text-underline-offset:2px;
  font:500 13px/1.4 var(--mono);white-space:nowrap}}
.src:hover{{text-decoration-thickness:2px}}
.note{{margin:8px 0 0;font:400 13px/1.45 var(--body);font-style:italic;color:var(--fg3)}}
.corrected-badge{{margin:8px 0 0;font:500 13px/1.45 var(--mono);color:var(--zw);border-left:2px solid var(--zw-b);padding-left:8px}}

/* ---- verbatim source excerpt ---- */
.src-quote{{margin:8px 0 0;font:400 13px/1.45 var(--body);color:var(--fg3);border-left:2px solid var(--rule);padding-left:8px}}
.src-quote summary{{cursor:pointer;font:600 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--soft);list-style:none;display:inline-flex;align-items:center;gap:5px}}
.src-quote summary::-webkit-details-marker{{display:none}}
.src-quote summary::before{{content:"+";font:500 11px/1 var(--mono)}}
.src-quote[open] summary::before{{content:"–"}}
.src-quote[open]{{padding-bottom:4px}}

/* ---- source disagreements ---- */
.contradiction{{margin:16px 0;background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 18px 16px}}
.ct-head{{font:600 11px/1.4 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--zr);margin:0 0 6px}}
.ct-note{{font:400 13px/1.45 var(--body);font-style:italic;color:var(--fg3);margin:0 0 10px}}
.ct-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0}}
.ct-grid .fact{{border-bottom:1px solid var(--line);padding:10px 0}}
.ct-grid .fact:last-child{{border-bottom:0}}
@media(min-width:600px){{
  .ct-grid{{gap:0 18px}}
  .ct-grid .fact{{border-bottom:1px solid var(--line);border-right:1px solid var(--line);padding:10px 14px 10px 0}}
  .ct-grid .fact:last-child{{border-right:0}}
}}

/* ---- stance chips (contradiction groups) ---- */
.stance-chip{{font:600 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;padding:3px 8px;border-radius:4px;margin:8px 0 -4px;display:inline-block}}
.st-pro{{color:var(--zg);background:var(--zg-b)}}
.st-con{{color:var(--zr);background:var(--zr-b)}}
.st-mix{{color:var(--zw);background:var(--zw-b)}}

/* ---- footnotes ---- */
.fnref{{font:600 10px/1 var(--mono);vertical-align:super;letter-spacing:.02em}}
.fnref a{{color:var(--teal);text-decoration:none}}
.fnref a:hover{{text-decoration:underline}}
.fnotes{{margin:14px 0 4px;max-width:68ch;border-top:1px solid var(--line);padding-top:8px}}
.fnotes .fn-lbl{{font:600 10px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);display:block;margin-bottom:4px}}
.fnotes ol{{margin:0;padding-left:18px}}
.fnotes li{{font-size:11.5px;line-height:1.5;color:var(--soft);margin:2px 0;overflow-wrap:anywhere}}
.fnotes a{{color:var(--teal);text-decoration:none}}
.fnotes a:hover{{text-decoration:underline}}

/* ---- To review ---- */
.review{{margin:64px 0 0;border:1px solid var(--rule);border-radius:12px;background:var(--card);
  padding:4px 26px 10px;box-shadow:0 1px 3px rgba(26,24,22,.04)}}
.review[open]{{padding-bottom:26px}}
.review>summary{{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:baseline;
  gap:6px 14px;padding:18px 0 14px}}
.review>summary::-webkit-details-marker{{display:none}}
.review>summary::before{{content:"+";font:500 15px/1 var(--mono);color:var(--soft);margin-right:2px}}
.review[open]>summary::before{{content:"–"}}
.rsum-h2{{font:700 clamp(19px,3.2vw,24px)/1.06 var(--disp);letter-spacing:-.02em}}
.rsum-n{{font:500 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--fg3)}}
.review>.sub{{font-size:15px;color:var(--soft);margin:0 0 16px;max-width:56ch;line-height:1.55}}
.rfact{{padding:14px 0;border-top:1px solid var(--line)}}
.rfact .claim{{font-size:15px;margin-bottom:7px}}
.rlabel{{border:1px solid var(--rule);color:var(--soft);border-radius:4px;padding:2px 7px;
  font:600 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase}}
.rwhy{{margin:7px 0 0;font:400 13px/1.45 var(--body);font-style:italic;color:var(--fg3)}}
.nolink{{color:var(--fg3);font:500 11px/1 var(--mono)}}

/* ---- colophon ---- */
.foot{{margin:64px 0 0;padding-top:20px;border-top:2px solid var(--ink);
  font:400 13px/1.55 var(--body);color:var(--soft);max-width:62ch}}
.foot .legend{{display:flex;flex-wrap:wrap;gap:8px 18px;margin:14px 0;font:500 11px/1 var(--mono)}}
.foot .legend span{{display:inline-flex;align-items:center;gap:7px}}
.foot b{{color:var(--ink);font-weight:600}}

@media print{{
  @page{{margin:18mm 16mm}}
  body{{background:#fff;color:#111;font-size:10.5pt;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  .wrap{{max-width:none;padding:0}}
  .sidenav{{display:none}}
  a{{color:var(--teal)}}
  .src,.narr a{{text-decoration-color:var(--teal)}}
  /* table of contents page: its own page after the cover */
  .toc-print{{display:block;break-before:page;break-after:page;padding-top:6mm}}
  .toc-print .kicker{{margin:0 0 18px}}
  .toc-print ol{{list-style:none;margin:0;padding:0;counter-reset:tp}}
  .toc-print li a{{display:flex;align-items:baseline;gap:14px;padding:10px 0;
    border-bottom:1px solid var(--line);color:#111;text-decoration:none}}
  .toc-print .tp-n{{font:600 13px/1.4 var(--mono);color:var(--soft);min-width:26px}}
  .toc-print .tp-t{{font:600 15px/1.3 var(--disp)}}
  /* expand collapsed sections — in PDF evidence and "To review" must be visible */
  details>summary{{display:none}}
  .evidence,.review{{display:block}}
  .evidence>:not(summary),.review>:not(summary){{display:block !important}}
  .review{{background:#fff;border:1px solid #bbb;box-shadow:none;padding:0;margin-top:32px}}
  .hcard,.funnel{{box-shadow:none}}
  /* avoid breaking semantic blocks across pages */
  .sec,.strip,.fact,.rfact,.tbl,.svz,.hero,.plan .ap li{{break-inside:avoid}}
  .sec-head h2,.tldr h3{{break-after:avoid}}
}}
@media(max-width:560px){{
  .wrap{{padding:32px 18px 64px}}
  .srcs{{margin-left:0;width:100%}}
}}
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
