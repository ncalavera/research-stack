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

Usage: python3 render_paged.py <topic>            (default: topic1)
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
# narratives_file: a bare filename (no "/") resolves against the TOPIC dir, not
# the repo root — otherwise "narratives.json" pointed at ROOT and the prose was
# lost silently (report with chapter headers but empty body). A slashed path
# (e.g. "topics/x/narratives.json") stays relative to ROOT.
_nf = cfg("narratives_file")
if not _nf:
    _narr_path = P.narratives(TOPIC)
elif "/" in _nf:
    _narr_path = ROOT / _nf
else:
    _narr_path = P.topic_dir(TOPIC) / _nf
NARR = load(_narr_path, {})
if not NARR and _narr_path.exists() is False:
    sys.stderr.write(
        f"⚠ render_paged: narratives file not found: {_narr_path} — "
        f"report will build WITHOUT prose (fact cards only).\n")

# Normalise narrative shape: a subagent may return either the flat form
# ({sec: prose, "_keypoints": {sec:[...]}, ...}) or the nested form
# ({sec: {prose, _keypoints, _so_what, _action_plan}}). Accept both — otherwise
# the renderer choked on a dict where it expected a prose string.
if any(isinstance(v, dict) and "prose" in v
       for k, v in NARR.items() if not k.startswith("_")):
    _flat = {}
    _kp = dict(NARR.get("_keypoints", {}))
    _sw = dict(NARR.get("_so_what", {}))
    _ap = list(NARR.get("_action_plan", []))
    for k, v in NARR.items():
        if k.startswith("_"):
            _flat[k] = v
        elif isinstance(v, dict):
            _flat[k] = v.get("prose", "")
            if v.get("_keypoints"):
                _kp[k] = v["_keypoints"]
            if v.get("_so_what"):
                _sw[k] = v["_so_what"]
            if v.get("_action_plan"):
                _ap.extend(v["_action_plan"])
        else:
            _flat[k] = v
    _flat["_keypoints"], _flat["_so_what"] = _kp, _sw
    if _ap:
        _flat["_action_plan"] = _ap
    NARR = _flat

SO_WHAT = NARR.get("_so_what", {})
KEYPOINTS = NARR.get("_keypoints", {})
TABLES = NARR.get("_tables", {})
# _action_plan: accept both bare strings and [label, text] pairs; the renderer
# expects pairs (bare strings broke unpacking under enumerate).
ACTION_PLAN = [
    x if (isinstance(x, (list, tuple)) and len(x) == 2) else ["", str(x)]
    for x in NARR.get("_action_plan", [])
]
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
  {note_html}
</article>"""


def contradiction_block(grp, fid_to_fact):
    """Render a contradiction group: header + member fact cards side by side in a CSS grid."""
    issue = esc(grp.get("issue", "sources disagree"))
    note = grp.get("note", "")
    note_html = f'<div class="ct-note">{esc(note)}</div>' if note else ""
    cards = "".join(fact_block(fid_to_fact[fid]) for fid in grp["fids"])
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
    return (f'<div class="keybox"><div class="kb-lbl">Key takeaways</div>'
            f'<ul class="keys">{lis}</ul></div>')


_NUMCELL_RE = re.compile(r"^[\d\s.,%×x+\-–—~≈/]+$")


def table_html(sec):
    t = TABLES.get(sec)
    if not t:
        return ""
    cols = t.get("cols", [])
    wide = " tbl-wide" if len(cols) >= 5 else ""
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = ""
    for row in t.get("rows", []):
        cells = ""
        for c in row:
            num = ' class="num"' if _NUMCELL_RE.match(str(c).strip() or "-") and any(ch.isdigit() for ch in str(c)) else ""
            cells += f"<td{num}>{esc(c)}</td>"
        body += f"<tr>{cells}</tr>"
    foot = f'<tfoot><tr><td colspan="{len(cols)}">{esc(t["foot"])}</td></tr></tfoot>' if t.get("foot") else ""
    cap = f'<figcaption>{esc(t["title"])}</figcaption>' if t.get("title") else ""
    return (f'<figure class="tbl{wide}">{cap}<table><thead><tr>{head}</tr></thead>'
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


# ---------- PAGED ASSEMBLY: A4 portrait, fixed pages ----------
# Design: consulting report (McKinsey conventions): cover with KPI strip,
# chapter = page, exhibits with takeaway and source line, footnotes at the
# bottom of each page, bibliography with full URLs, appendices compact, dark colophon.

by_sec = {}
for f in FACTS:
    by_sec.setdefault(f["section"], []).append(f)
ordered = [s for s in SECTION_ORDER if s in by_sec] + [s for s in by_sec if s not in SECTION_ORDER]

# chapter accents: 01 teal · 02 coral · 03 amber · 04 plum · 05 yandex red · 06 blue · 07 navy
ACCENTS = ["#0F6B5C", "#C2452D", "#B07D10", "#6A3D7D", "#C0392B", "#2456A6", "#1B2A4A"]


def acc(i):
    return ACCENTS[(i - 1) % len(ACCENTS)]


def _mix(hexc, frac):
    """Tint accent on white: frac — colour fraction."""
    h = hexc.lstrip("#")
    r, g, b = (int(h[j:j + 2], 16) for j in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(round(c * frac + 255 * (1 - frac)) for c in (r, g, b))


_RUNIN_RE = re.compile(r"<b>([^<]{2,60}[.:])</b>")


def runinize(h):
    """Run-ins in prose (Principle. / Myth: / What we do.) → accent colour of chapter."""
    return _RUNIN_RE.sub(r'<b class="runin">\1</b>', h)


def strip_tags(h):
    h = re.sub(r"<sup.*?</sup>", "", h, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()


def ensure_dot(t):
    t = t.strip()
    return t if t.endswith((".", "!", "?", "…")) else t + "."


# --- footnote ordering: executive summary first, then chapters in order ---
_tldr_override = NARR.get("_tldr")
if isinstance(_tldr_override, list) and _tldr_override:
    _tldr_items = [footnotize(t) for t in _tldr_override]
else:
    _tldr_items = [f'{esc(f["text"])} ({src_link(f.get("best_source", ""), paren=False)})'
                   for f in pick_tldr() if f.get("best_source")]

chapters = []
PROSE_WARN = []
for i, sec in enumerate(ordered, 1):
    items = sorted(by_sec[sec], key=lambda f: (
        CONF_ORDER.get(f.get("confidence"), 3),
        0 if f.get("best_class") == "A" else (1 if f.get("best_class") == "B" else 2),
        -f.get("engines_count", 0)))
    cc = {"A": 0, "B": 0, "C": 0}
    for f in items:
        cc[f.get("best_class", "C")] = cc.get(f.get("best_class", "C"), 0) + 1
    cls_summary = " · ".join(f"{k} {cc[k]}" for k in ("A", "B", "C") if cc[k])
    narrative = NARR.get(sec, "")
    narr = runinize(footnotize(narrative)) if narrative else ""
    _ptext = re.sub(r"<[^>]+>", " ", narrative)
    _nsent = len([s for s in re.split(r"[.!?]+", _ptext) if s.strip()])
    # paged = teaching format (Principle → Mechanism → Myth/Reality → What we do),
    # so the limit is wider than render_final (4/600): we only catch a wall of text.
    if _nsent > 16 or len(_ptext) > 2000:
        PROSE_WARN.append(f"  · «{sec}»: {_nsent} sentences, {len(_ptext)} chars (limit 16 / 2000)")
    chapters.append({"i": i, "sec": sec, "items": items, "cls_summary": cls_summary, "narr": narr})

# ---------- "To review": dedup rejected ----------
rec_raw = REJ.get("recovery_candidates", [])
seen_txt, rec = {}, []
for r in sorted(rec_raw, key=lambda x: (0 if x.get("source_alive") else 1)):
    key = " ".join((r.get("text") or "").lower().split())[:120]
    if key in seen_txt:
        continue
    seen_txt[key] = True
    rec.append(r)
rec = sorted(rec, key=lambda x: (0 if x.get("source_alive") else 1))

summ = REJ.get("summary", {})
n_facts = len(FACTS)
n_rev = len(rec)
engines_used = sorted({ENGINE.get(p["engine"], p["engine"]) for f in FACTS for p in f["provenance"]})
_MONTHS_EN = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
_td = datetime.date.today()
today_ru = f"{_MONTHS_EN[_td.month - 1]} {_td.day}, {_td.year}"

page_title = cfg("page_title") or POOL.get("topic", TOPIC)
title_html = cfg("title_html") or esc(POOL.get("topic", TOPIC))
footer_methods = cfg("footer_methods") or "Sources found by deep-search engines; for each fact you can see which engines and how many."
_stale_years_val = int(cfg("stale_years") or 3)
footer_methods = footer_methods + f" Recency: ⏳ next to a fact means the source is older than {_stale_years_val} years."
footer_note = cfg("footer_note")

# Tag for running footer and columns: from settings (page_title + kicker), without hardcoded examples.
REPORT_TAG = cfg("report_tag") or (
    (page_title or POOL.get("topic", TOPIC))
    + (f" · {cfg('kicker')}" if cfg("kicker") else "")
)
# Assembly source name for exhibit/colophon captions: from settings or neutral.
BUILD_SRC = cfg("build_source") or "fact-check funnel research-stack"
COVER_PREFIX = cfg("cover_prefix")  # e.g. "Acme · "; empty → no prefix

# ---------- exhibits (consulting convention) ----------
_EXH_N = [0]


def exhibit(title, takeaway, content_html, source_line):
    _EXH_N[0] += 1
    t = f" · {esc(title)}" if title else ""
    return (f'<figure class="exh"><div class="exh-lbl">Exhibit {_EXH_N[0]}{t}</div>'
            f'<p class="exh-take">{esc(ensure_dot(takeaway))}</p>{content_html}'
            f'<div class="exh-src">Source: {esc(source_line)}</div></figure>')


def table_naked(sec):
    """Table without figcaption — title goes into the exhibit label row."""
    return re.sub(r"<figcaption>.*?</figcaption>", "", table_html(sec), flags=re.S)


# ---------- pages ----------
PAGES = []   # {"cls","body","foot"(bool)}


def add_page(cls, body, foot=True):
    PAGES.append({"cls": cls, "body": body, "foot": foot})
    return len(PAGES) + 1   # page number accounting for cover added at the start


TOC = []  # (marker, colour, title, page number)

# --- mapping TLDR findings to chapters: by intersection of source links ---
def _raw_links(h):
    return set(re.findall(r"href='([^']+)'", h or ""))


_tldr_raw = _tldr_override if isinstance(_tldr_override, list) else []
_sec_links = {c["i"]: _raw_links(NARR.get(c["sec"], "")) for c in chapters}
TLDR_CH = {}   # finding index (0-based) -> chapter number with evidence
for _j, _t in enumerate(_tldr_raw):
    _tl = _raw_links(_t)
    _best, _bestn = None, 0
    for _c in chapters:
        _ov = len(_tl & _sec_links[_c["i"]])
        if _ov > _bestn:
            _best, _bestn = _c["i"], _ov
    if _best is not None:
        TLDR_CH[_j] = _best
CH_TLDR = {}   # chapter number -> index of first matched finding
for _j in sorted(TLDR_CH):
    CH_TLDR.setdefault(TLDR_CH[_j], _j)

# --- 2. Executive summary ---
xs_lis = "".join(
    f'<li><i style="color:{acc(TLDR_CH[j]) if j in TLDR_CH else "var(--navy)"}">{j + 1:02d}</i><div>{t}</div></li>'
    for j, t in enumerate(_tldr_items))
exec_body = (
    '<header class="pg-head"><div class="eyebrow">Executive summary</div>'
    f'<h2>{esc(cfg("tldr_title", "If you read only this"))}</h2>'
    f'<p class="ph-sub">{len(_tldr_items)} key findings of the research; the number colour points to the chapter '
    f'with evidence. Each finding rests on verified sources — footnotes at the bottom of the page.</p></header>'
    f'<ol class="xs">{xs_lis}</ol>')
_p = add_page("pg-exec", exec_body)
TOC.append(("ES", "var(--navy)", cfg("tldr_title", "If you read only this"), _p))

# --- 3–9. Chapters: one chapter = one page ---
MATRIX_SECS = {s for s in TABLES if len(TABLES[s].get("cols", [])) >= 5}
matrix_page_no = None

_FNSUP_RE = re.compile(r'<sup class="fnref">(.*?)</sup>', re.S)


def _page_fns(body):
    nums = set()
    for m in _FNSUP_RE.finditer(body):
        nums.update(int(x) for x in re.findall(r">(\d+)</a>", m.group(1)))
    return sorted(nums)


def est_h(text, cpl, line_h, extra):
    lines = max(1, -(-len(text) // cpl))
    return lines * line_h + extra


def quote_block(quote, source):
    """Return indented italic quote line for print-first rendering. HTML-escaped."""
    if not quote:
        return ""
    link = f'<a href="{esc(source)}" target="_blank" rel="noopener">{esc(domain(source))}</a>' if source else ""
    sep = " — " if link else ""
    return f'<div class="ev-quote">«{esc(quote)}»{sep}{link}</div>'


def stance_chip(stance):
    """Render stance chip for contradiction group member (paged renderer)."""
    if not stance:
        return ""
    STANCE_PROPS = {
        "поддерживает": ("st-pro", "▲ supports"),
        "опровергает": ("st-con", "▼ refutes"),
        "смешанно": ("st-mix", "◆ mixed"),
    }
    cls, label = STANCE_PROPS.get(stance, ("st-mix", f"◆ {esc(stance)}"))
    return f'<span class="stance-chip {cls}">{label}</span>'


def contradiction_block_paged(grp, fid_to_fact):
    """Minimal contradiction rendering for paged renderer (appendix A context)."""
    issue = esc(grp.get("issue", "sources disagree"))
    note = grp.get("note", "")
    note_html = f'<div class="ev-ct-note">⚡ {issue}{" — " + esc(note) if note else ""}</div>'
    stances = grp.get("stances", {})
    cards = ""
    for fid in grp["fids"]:
        f = fid_to_fact.get(fid)
        if f:
            chip = stance_chip(stances.get(fid))
            cards += chip + ev_row(f)
    return f'<div class="ev-ct">{note_html}{cards}</div>'


def ev_row(f):
    """Compact fact card (grey box): claim · class · engines · confidence · domain."""
    cls = f.get("best_class") or "C"
    conf = f.get("confidence", "medium")
    ec = f.get("engines_count", 1)
    best = f.get("best_source") or next((p.get("source") for p in f.get("provenance", []) if p.get("source")), "")
    corrected = (f.get("corrected") or "").strip()
    cor = f'<em class="ev-cor"> ⚠ source says: «{esc(corrected)}»</em>' if corrected else ""
    note = f.get("note")
    nt = f'<em class="ev-cor"> · {esc(note)}</em>' if note else ""
    quote = (f.get("quote") or "").strip()
    qt = f'<div class="ev-quote">«{esc(quote)}»</div>' if quote else ""
    link = f'<a href="{esc(best)}" target="_blank" rel="noopener">{esc(domain(best))}</a>' if best else ""
    meta = (f'Class {cls} · {ec} {plural(ec, "engine", "engines", "engines")} · '
            f'confidence {CONF_EN.get(conf, conf)}')
    return (f'<article class="ev"><p>{esc(f["text"])}{cor}{nt}</p>'
            f'{qt}'
            f'<div class="ev-m"><span class="cls cls-{cls}">{cls}</span><span>{meta}</span>{link}</div></article>')


for ch in chapters:
    i, sec, items = ch["i"], ch["sec"], ch["items"]
    nf = len(items)
    head = (f'<header class="ch-head">'
            f'<div class="ch-tag">Chapter {i:02d}</div>'
            f'<h2>{esc(sec)}</h2>'
            f'<div class="ch-sub">Evidence: {nf} {plural(nf, "fact", "facts", "facts")} · {ch["cls_summary"]} · full list — appendix A</div>'
            f'</header>')
    kb = keypoints_html(sec)
    narr = f'<div class="narr cols">{ch["narr"]}</div>' if ch["narr"] else ""
    # pull quote: reprise of the executive summary finding matched to this chapter by sources
    pull, pq = "", ""
    if i in CH_TLDR:
        pq = strip_tags(_tldr_items[CH_TLDR[i]])
        pull = f'<div class="pull">{esc(pq)}</div>'
    tbl = ""
    if sec in TABLES and sec not in MATRIX_SECS:
        t = TABLES[sec]
        kp = (KEYPOINTS.get(sec) or [""])[0]
        tbl = exhibit(t.get("title", ""), kp, table_naked(sec),
                      f"{BUILD_SRC}; chapter {i:02d}, {nf} verified facts")
    nxt = ('<div class="next-note">Decision matrix by page type — next page →</div>'
           if sec in MATRIX_SECS else "")
    # --- page fill estimate → adaptive evidence extract ---
    _pts = KEYPOINTS.get(sec) or []
    _plain = strip_tags(ch["narr"])
    h_est = 100.0 + 37 * (-(-len(sec) // 34))                        # chapter opener
    h_est += 48 + (-(-len(_pts) // 2)) * 33                          # keybox, 2 columns
    h_est += len(_plain) * 0.215 + 16                                # prose, 2 columns
    if pull:
        h_est += (-(-len(pq) // 78)) * 25 + 30
    if tbl:
        h_est += 80 + len(TABLES[sec].get("rows", [])) * 28
    if nxt:
        h_est += 32
    _nfn = len(_page_fns(narr))
    h_est += 42 + (-(-_nfn // 2)) * 13.5                             # footnotes + folio
    # overflow → compress typography with tight class (content unchanged)
    tight = ""
    if h_est > 990:
        tight = " tight"
        h_est *= 0.87
    # evidence is entirely in appendix B — no excerpts on chapter pages
    ev_extract = ""

    # underflow → loosen typography with roomy class (page breathes instead of sitting empty)
    if not tight and h_est < 880:
        tight = " roomy"
    body = head + kb + narr + pull + tbl + ev_extract + nxt
    _p = add_page(f"pg-ch acc-{min(i, 7)}{tight}", body)
    TOC.append((f"{i:02d}", acc(i), sec, _p))
    # --- 10. Decision matrix: full page (money page) ---
    if sec in MATRIX_SECS:
        t = TABLES[sec]
        kp = (KEYPOINTS.get(sec) or [""])[0]
        mt = exhibit(t.get("title", ""), kp, table_naked(sec),
                     f"{BUILD_SRC}; n={n_facts} verified facts")
        mhead = (f'<header class="pg-head"><div class="eyebrow" style="color:{acc(i)}">Chapter {i:02d} · continued</div>'
                 f'<h2>Decision matrix</h2>'
                 f'<p class="ph-sub">Six page types for example.inc: who writes, length, structure, markup, recency and risk. '
                 f'Items marked "(judgment)" are team positions, not confirmed facts.</p></header>')
        matrix_page_no = add_page(f"pg-matrix acc-{min(i, 7)}", mhead + mt)
        TOC.append(("◆", acc(i), "Decision matrix — full page", matrix_page_no))

# --- 11. Action plan ---
if ACTION_PLAN:
    ap_rows = "".join(
        f'<li><i style="color:{acc((j - 1) % 7 + 1)}">{j:02d}</i>'
        f'<div><span class="ap-sec" style="color:{acc((j - 1) % 7 + 1)}">{esc(s)}</span>'
        f'<span class="ap-act">{esc(a)}</span></div></li>'
        for j, (s, a) in enumerate(ACTION_PLAN, 1))
    plan_body = ('<header class="pg-head"><div class="eyebrow">What we do</div>'
                 '<h2>Action plan</h2>'
                 f'<p class="ph-sub">{len(ACTION_PLAN)} steps — each follows from the chapter with the same colour.</p></header>'
                 f'<ol class="ap">{ap_rows}</ol>')
    _p = add_page("pg-plan", plan_body)
    TOC.append(("→", "var(--navy)", "Action plan", _p))

# --- 12. Methodology + Sources (bibliography, full URLs) ---
bib_rows = "".join(
    f'<li>{esc(lbl)} — <a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>'
    for lbl, u in FOOTNOTES)
meth_body = ('<header class="pg-head"><div class="eyebrow">Methodology and sources</div>'
             '<h2>How this report was built</h2></header>'
             f'<div class="methods"><div class="m-lbl">Methodology and limitations</div>'
             f'<p>{esc(footer_methods)}</p>'
             + (f'<p class="m-note">{esc(footer_note)}</p>' if footer_note else "") +
             '</div>'
             f'<div class="bib"><div class="m-lbl">Sources · {len(FOOTNOTES)} · sequential footnote numbering</div>'
             f'<ol>{bib_rows}</ol></div>')
_p = add_page("pg-meth", meth_body)
TOC.append(("§", "var(--navy)", "Methodology and sources", _p))

# ---------- appendices: manual pagination by height estimate ----------


def paginate(blocks, cap_first, cap_rest):
    pages, cur, used, cap = [], [], 0.0, cap_first
    for h, b in blocks:
        if cur and used + h > cap:
            pages.append(cur)
            cur, used, cap = [], 0.0, cap_rest
        cur.append(b)
        used += h
    if cur:
        pages.append(cur)
    return pages


# --- Appendix A: evidence — all facts by chapter ---
ev_blocks = []
for ch in chapters:
    i, sec = ch["i"], ch["sec"]
    hdr = (f'<div class="ev-grp" style="color:{acc(i)};border-color:{acc(i)}">'
           f'{i:02d} · {esc(sec)} · {len(ch["items"])}</div>')
    for j, f in enumerate(ch["items"]):
        corrected = (f.get("corrected") or "").strip()
        b = ev_row(f)
        h = est_h(f["text"] + corrected, 55, 12.2, 32.0)
        if j == 0:
            # group header glued to first fact — does not become a widow at the bottom of a column
            ev_blocks.append((h + 42.0, f'<div class="ev-pair">{hdr}{b}</div>'))
        else:
            ev_blocks.append((h, b))

_ev_chunks = paginate(ev_blocks, 1600.0, 1820.0)
appB_page_no = None
for k, chunk in enumerate(_ev_chunks):
    if k == 0:
        hd = ('<header class="pg-head app"><div class="eyebrow">Appendix A</div>'
              '<h2>Evidence</h2>'
              f'<p class="ph-sub">All {n_facts} verified facts by chapter. Source class: '
              f'<span class="cls cls-A">A</span> primary source · science · gov, '
              f'<span class="cls cls-B">B</span> secondary, '
              f'<span class="cls cls-C">C</span> blog · vendor. Domain — best live source for the fact; '
              f'engines listed in methodology.</p></header>')
    else:
        hd = f'<div class="app-cont">Appendix A · evidence · continued ({k + 1}/{len(_ev_chunks)})</div>'
    _bal = " bal" if k == len(_ev_chunks) - 1 and len(_ev_chunks) > 1 else ""
    body = hd + f'<div class="app-cols{_bal}">{"".join(chunk)}</div>'
    _p = add_page("pg-app", body)
    if k == 0:
        appB_page_no = _p
TOC.append(("B", "var(--fg3)", "Appendix A — evidence", appB_page_no))

# --- Appendix B: rejected claims — ultra-compact table ---
_RTAG = {"BROKEN_SOURCE": "broken link", "MISATTRIBUTED": "fact not on source",
         "UNSOURCED": "no link"}
_rcounts = {}
for r in rec:
    _rcounts[r.get("label", "?")] = _rcounts.get(r.get("label", "?"), 0) + 1
rej_summary = " · ".join(f"{_RTAG.get(k, k)} — {v}" for k, v in sorted(_rcounts.items(), key=lambda x: -x[1]))

rej_rows = []
for r in rec:
    txt = r.get("text", "")
    src = r.get("source")
    dom = domain(src) if src else "—"
    tag = _RTAG.get(r.get("label"), r.get("label", ""))
    row = (f'<tr><td class="rj-c">{esc(txt)}</td><td class="rj-t">{esc(tag)}</td>'
           f'<td class="rj-d">{esc(dom)}</td></tr>')
    rej_rows.append((est_h(txt, 80, 11.6, 9.5), row))

_REJ_THEAD = ('<thead><tr><th>Claim</th><th>Reason</th><th>Candidate source</th></tr></thead>')
_rej_chunks = paginate(rej_rows, 820.0, 930.0)
appA_page_no = None
for k, chunk in enumerate(_rej_chunks):
    if k == 0:
        hd = ('<header class="pg-head app"><div class="eyebrow">Appendix B</div>'
              '<h2>Rejected claims</h2>'
              f'<p class="ph-sub">{n_rev} {plural(n_rev, "claim", "claims", "claims")} did not pass fact-check gates: '
              f'{rej_summary}. Out of {summ.get("total_rejected", "—")} rejected, after deduplication {n_rev} remain with a candidate source (live sources first) — open and decide for yourself.</p></header>')
    else:
        hd = f'<div class="app-cont">Appendix B · rejected claims · continued ({k + 1}/{len(_rej_chunks)})</div>'
    body = hd + f'<table class="rjt">{_REJ_THEAD}<tbody>{"".join(chunk)}</tbody></table>'
    _p = add_page("pg-app", body)
    if k == 0:
        appA_page_no = _p
TOC.append(("A", "var(--fg3)", "Appendix B — rejected claims", appA_page_no))

# --- last page: authors and colophon on dark field ---
end_body = (f'<div class="end-inner">'
            f'<div class="end-top"><div class="eyebrow end-eb">{esc(cfg("kicker","")) }</div>'
            f'<h2 class="end-h">{title_html}</h2></div>'
            f'<div class="end-grid">'
            f'<div><div class="end-lbl">Authors</div>'
            # Byline author is configurable via the topic config "author" field;
            # absent → a generic engine label (no hardcoded personal name).
            + (f'<p><b>{esc(cfg("author"))}</b> — research &amp; engine</p>' if cfg("author")
               else '<p><b>Research &amp; fact-check engine</b></p>') +
            f'<p><b>Claude (Anthropic)</b> — fact-check funnel research-stack</p></div>'
            f'<div><div class="end-lbl">Project</div>'
            f'<p><b>{esc(cfg("kicker") or page_title)}</b></p>'
            f'{("<p>"+esc(footer_note)+"</p>") if footer_note else ""}</div>'
            f'<div><div class="end-lbl">Published</div>'
            f'<p>{today_ru}</p>'
            f'<p>{n_facts} verified facts · {len(engines_used)} engines · {n_rev} rejected</p></div>'
            f'</div>'
            + (f'<p class="end-note">{esc(footer_note)} Every fact is confirmed by a live source; '
               f'source class and confidence are listed in appendix A.</p>' if footer_note else "") +
            f'</div>')
_p = add_page("pg-end", end_body, foot=False)

# ---------- cover (page 1): absorbs table of contents ----------
cover_kick = (COVER_PREFIX or "") + cfg("kicker", "fact-check funnel research-stack")
toc_rows = "".join(
    f'<div class="ct-row"><span class="ct-n" style="color:{c}">{n}</span>'
    f'<span class="ct-t">{esc(t)}</span><span class="ct-p">{p}</span></div>'
    for n, c, t, p in TOC)
_ig = INFOGRAPHIC if INFOGRAPHIC.get("stats") else {"stats": [], "title": "", "caption": ""}
_cap = _ig.get("caption", "")
_cap_first, _cap_rest = (_cap.split(". ", 1) + [""])[:2] if ". " in _cap else (_cap, "")
stats_html = "".join(
    f'<div class="cs" style="border-color:{acc(j + 1)}">'
    f'<div class="cs-v" style="color:{acc(j + 1)}">{esc(s.get("value", ""))}'
    f'<span class="cs-u">{esc(s.get("unit", ""))}</span></div>'
    f'<div class="cs-l">{esc(s.get("label", ""))}</div></div>'
    for j, s in enumerate(_ig["stats"]))
cover_body = (
    f'<div class="cv-band">'
    f'<div class="cv-kick">{esc(cover_kick)}</div>'
    f'<h1>{title_html}</h1>'
    f'<p class="cv-dek">{esc(cfg("dek"))}</p>'
    f'<div class="cv-meta"><span>{today_ru}</span><span>{n_facts} verified facts</span>'
    f'<span>{len(engines_used)} deep-search engines</span><span>{n_rev} claims rejected</span></div>'
    f'</div>'
    f'<div class="cv-body">'
    f'<div class="cv-toc"><div class="cv-lbl">Contents</div>{toc_rows}</div>'
    f'<div class="cv-stats"><div class="cv-lbl">{esc(_ig.get("title", "Answer in numbers"))}</div>'
    + (f'<p class="exh-take cv-take">{esc(ensure_dot(_cap_first))}</p>' if _cap_first else "") +
    f'<div class="cs-grid">{stats_html}</div>'
    f'<div class="exh-src">{esc(_cap_rest)}{" · " if _cap_rest else ""}Source: {BUILD_SRC}; n={n_facts} verified facts</div>'
    f'</div></div>')
PAGES.insert(0, {"cls": "pg-cover", "body": cover_body, "foot": False})

# ---------- page footnotes: format "Name — domain, year", full URLs in bibliography ----------
def fn_entry(n):
    lbl, u = FOOTNOTES[n - 1]
    m = SRC.get(u) or {}
    yr = f", {m['year']}" if m.get("year") else ""
    return (f'<div class="pfn"><i>{n}</i><span><a href="{esc(u)}" target="_blank" rel="noopener">'
            f'{esc(lbl)}</a> — {esc(domain(u))}{yr}</span></div>')


pages_html = []
total_pages = len(PAGES)
for k, p in enumerate(PAGES, 1):
    foot = ""
    if p.get("foot", True):
        nums = _page_fns(p["body"])
        fns = (f'<div class="pfns">{"".join(fn_entry(n) for n in nums)}</div>') if nums else ""
        foot = (f'<footer class="page-foot">{fns}'
                f'<div class="pf-strip"><span class="pf-ttl">{esc(REPORT_TAG)}</span>'
                f'<span class="pf-num">{k} / {total_pages}</span></div></footer>')
    elif p["cls"] == "pg-end":
        foot = (f'<footer class="page-foot end-foot"><div class="pf-strip">'
                f'<span class="pf-ttl">{esc(REPORT_TAG)}</span>'
                f'<span class="pf-num">{k} / {total_pages}</span></div></footer>')
    pages_html.append(f'<section class="page {p["cls"]}" id="pg{k}">{p["body"]}{foot}</section>')

# ---------- sidebar navigation (screen only; hidden in print) ----------
# Section anchors already exist (id="pgN"); page numbers in TOC point to the same sections.
_sn_rows = "".join(
    f'<li><a href="#pg{p}"><span class="sn-n" style="color:{c}">{n}</span>'
    f'<span class="sn-t">{esc(t)}</span></a></li>'
    for n, c, t, p in TOC)
sidenav_html = (f'<nav class="sidenav" aria-label="Contents">'
                f'<a class="sn-home" href="#pg1">{esc(cover_kick)}</a>'
                f'<div class="sn-lbl">Contents</div><ol>{_sn_rows}</ol></nav>')

# scroll-spy: highlight active section (screen; does not affect print)
SIDENAV_JS = """<script>
(function(){
  var map={},all=[];
  document.querySelectorAll('.sidenav li a[href^="#"]').forEach(function(a){
    map[a.getAttribute('href').slice(1)]=a;all.push(a);});
  if(!all.length||!('IntersectionObserver' in window))return;
  var obs=new IntersectionObserver(function(es){
    es.forEach(function(e){
      if(!e.isIntersecting)return;
      var a=map[e.target.id];if(!a)return;
      all.forEach(function(x){x.classList.remove('on')});
      a.classList.add('on');});
  },{rootMargin:'-12% 0px -76% 0px'});
  document.querySelectorAll('section.page[id]').forEach(function(s){obs.observe(s)});
})();
</script>"""

# ---------- CSS ----------
ACC_CSS = "".join(
    f".acc-{i}{{--acc:{c};--acc-t:{_mix(c, .09)};--acc-t2:{_mix(c, .16)}}}"
    for i, c in enumerate(ACCENTS, 1))

CSS = """
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
:root{--paper:#fff;--ink:#1a1a1a;--soft:#43484f;--fg3:#6a7077;--line:#e4e6e9;--rule:#c4c8cd;
  --navy:#1b2a4a;--card:#f4f5f7;
  --disp:"Source Serif 4",Georgia,"Times New Roman",serif;
  --body:"Source Sans 3","Helvetica Neue",Arial,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,monospace;
  --acc:#1b2a4a;--acc-t:#edeff4;--acc-t2:#dde2ec}
html,body{margin:0;padding:0}
body{background:#53565b;font:400 11px/1.5 var(--body);color:var(--ink);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit;text-decoration:none}

/* ---- page: A4 portrait, fixed ---- */
.page{width:210mm;height:297mm;padding:13mm 15mm 11mm;display:flex;flex-direction:column;
  overflow:hidden;position:relative;background:var(--paper);margin:0 auto 18px;
  box-shadow:0 4px 22px rgba(0,0,0,.45);break-after:page}
@media print{
  body{background:#fff;padding:0}
  .page{margin:0;box-shadow:none}
  @page{size:A4 portrait;margin:0}
}

/* ---- eyebrow: letterspaced small-caps sans (not mono) ---- */
.eyebrow{font:700 9px/1 var(--body);letter-spacing:.24em;text-transform:uppercase;color:var(--navy)}

/* ---- running page footer ---- */
.page-foot{margin-top:auto;padding-top:6px}
.pfns{border-top:1px solid var(--rule);padding:6px 0 5px;columns:2;column-gap:24px}
.pfn{display:flex;gap:6px;font:400 8.7px/1.38 var(--body);color:var(--soft);
  break-inside:avoid;padding:1.5px 0}
.pfn i{font:700 7.8px/1.5 var(--body);font-style:normal;color:var(--acc);min-width:13px;
  text-align:right;flex:none;font-variant-numeric:tabular-nums}
.pfn a{color:var(--ink);font-weight:600}
.pf-strip{border-top:2px solid var(--ink);margin-top:5px;padding-top:5px;display:flex;
  justify-content:space-between;align-items:baseline}
.pf-ttl{font:700 8.7px/1 var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--fg3)}
.pf-num{font:700 9.5px/1 var(--body);color:var(--ink);font-variant-numeric:tabular-nums}

/* ---- cover ---- */
.pg-cover{padding:0}
.cv-band{background:var(--navy);color:#fff;padding:17mm 15mm 10mm}
.cv-kick{font:700 9.5px/1 var(--body);letter-spacing:.3em;text-transform:uppercase;color:#9db0d4;
  margin:0 0 24px;display:flex;align-items:center;gap:14px}
.cv-kick::after{content:"";flex:1;height:1px;background:rgba(255,255,255,.28)}
.cv-band h1{font:600 29px/1.18 var(--disp);letter-spacing:-.012em;margin:0 0 15px}
.cv-dek{font:400 13px/1.6 var(--body);color:#c6d1e6;max-width:62ch;margin:0 0 22px}
.cv-meta{display:flex;gap:8px 24px;flex-wrap:wrap;border-top:1px solid rgba(255,255,255,.25);
  padding-top:11px;font:700 8.5px/1.3 var(--body);letter-spacing:.12em;text-transform:uppercase;color:#9db0d4}
.cv-body{flex:1;display:flex;flex-direction:column;padding:8mm 15mm 9mm;gap:6.5mm;min-height:0}
.cv-lbl{font:700 9px/1 var(--body);letter-spacing:.24em;text-transform:uppercase;color:var(--navy);
  margin-bottom:9px;display:flex;gap:12px;align-items:center}
.cv-lbl::after{content:"";flex:1;height:1px;background:var(--rule)}
.ct-row{display:flex;align-items:baseline;gap:11px;padding:6px 0;border-bottom:1px solid var(--line);
  font:500 11.4px/1.3 var(--body)}
.ct-row:last-child{border-bottom:0}
.ct-n{font:700 9px/1 var(--body);min-width:20px;letter-spacing:.04em}
.ct-t{flex:1}
.ct-p{font:700 9.5px/1 var(--body);color:var(--fg3);font-variant-numeric:tabular-nums}
.cv-stats{margin-top:auto}
.cv-take{margin:0 0 10px}
.cs-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px 18px}
.cs{border-left:2.5px solid var(--line);padding-left:10px}
.cs-v{font:600 31px/1 var(--disp);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.cs-u{font:700 8.5px/1 var(--body);letter-spacing:.08em;text-transform:uppercase;margin-left:5px;color:var(--fg3)}
.cs-l{font:400 9.6px/1.45 var(--body);color:var(--soft);margin-top:6px}

/* ---- header for non-chapter pages ---- */
.pg-head{border-bottom:2px solid var(--navy);padding-bottom:11px;margin-bottom:13px}
.pg-head .eyebrow{margin-bottom:8px}
.pg-head h2{font:600 24px/1.12 var(--disp);letter-spacing:-.012em;margin:0}
.ph-sub{font:400 10.4px/1.5 var(--body);color:var(--soft);margin:7px 0 0;max-width:78ch}
.pg-head.app{border-color:var(--rule)}
.pg-head.app .eyebrow{color:var(--fg3)}
.app-cont{font:700 8.7px/1 var(--body);letter-spacing:.18em;text-transform:uppercase;color:var(--fg3);
  border-bottom:1px solid var(--rule);padding-bottom:7px;margin-bottom:10px}

/* ---- executive summary ---- */
.xs{list-style:none;margin:4px 0 0;padding:0}
.xs li{display:flex;gap:17px;padding:18px 0;border-bottom:1px solid var(--line);align-items:baseline}
.xs li:last-child{border-bottom:0}
.xs li i{font:600 21px/1 var(--disp);font-style:normal;flex:none;min-width:34px;font-variant-numeric:tabular-nums}
.xs li div{font:400 14.3px/1.66 var(--body)}
.xs li div a{color:var(--ink)}

/* ---- chapter: opener ---- */
.ch-head{border-bottom:2.5px solid var(--acc);padding-bottom:11px;margin-bottom:12px}
.ch-tag{display:inline-block;border:1.5px solid var(--acc);color:var(--acc);padding:5px 10px 4px;
  font:700 9.5px/1 var(--body);letter-spacing:.24em;text-transform:uppercase;margin-bottom:11px}
.ch-head h2{font:600 29px/1.1 var(--disp);letter-spacing:-.014em;margin:0 0 8px}
.ch-sub{font:700 8.6px/1.4 var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--fg3)}

/* ---- key takeaways ---- */
.keybox{background:var(--acc-t);border-left:3px solid var(--acc);padding:12px 16px 9px;margin:0 0 13px}
.kb-lbl{font:700 8.8px/1 var(--body);letter-spacing:.22em;text-transform:uppercase;color:var(--acc);margin:0 0 6px}
.keys{margin:0;padding:0;list-style:none;columns:2;column-gap:24px}
.keys li{position:relative;padding:4.5px 0 4.5px 14px;font:400 11px/1.5 var(--body);break-inside:avoid;border:0}
.keys li::before{content:"";position:absolute;left:0;top:12px;width:7px;height:2px;background:var(--acc)}

/* ---- prose: two columns, run-ins in accent ---- */
.narr{font:400 12.1px/1.62 var(--body)}
.narr.cols{columns:2;column-gap:26px}
.narr p{margin:0 0 9px}
.narr b{font-weight:600;color:var(--ink)}
.narr b.runin{color:var(--acc)}
.narr a{color:var(--ink)}
.fnref{font:700 8.2px/0 var(--body);vertical-align:super;letter-spacing:.02em}
.fnref a{color:var(--acc)}

/* ---- pull quote: chapter finding reprise ---- */
.pull{border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin:12px 0 4px;
  padding:13px 2px;font:600 17px/1.45 var(--disp);color:var(--acc);letter-spacing:-.005em}

/* ---- spacious typography for airy chapters ---- */
.roomy .ch-head h2{font-size:31px}
.roomy .keys li{font-size:11.7px;padding:5.5px 0 5.5px 14px}
.roomy .keys li::before{top:13px}
.roomy .keybox{padding:14px 17px 11px}
.roomy .narr{font-size:12.9px;line-height:1.66}
.roomy .narr p{margin-bottom:11px}
.roomy .pull{font-size:18.5px;padding:15px 2px;margin:14px 0 6px}
.roomy .chev{gap:9px 20px}
.roomy .ev{padding:10px 12px 9px}
.roomy .ev p{font-size:10.2px;line-height:1.5}
.roomy .chev-lbl{margin-top:18px;padding-top:11px}

/* ---- compressed typography for dense chapters (content unchanged) ---- */
.tight .ch-head h2{font-size:25px}
.tight .ch-head{padding-bottom:9px;margin-bottom:10px}
.tight .keybox{padding:9px 13px 6px;margin-bottom:10px}
.tight .keys li{font-size:10.2px;padding:3px 0 3px 13px}
.tight .keys li::before{top:10px}
.tight .narr{font-size:11.1px;line-height:1.55}
.tight .narr p{margin-bottom:7px}
.tight .pull{font-size:14.5px;padding:9px 2px;margin:8px 0 2px}
.tight .exh-take{font-size:11.6px;margin-bottom:7px}
.tight .tbl table{font-size:9.5px;line-height:1.4}
.tight .tbl td{padding:5px 7px}
.tight .exh{margin-top:9px}

/* ---- evidence extract on chapter page ---- */
.chev-lbl{font:700 8.8px/1.3 var(--body);letter-spacing:.18em;text-transform:uppercase;color:var(--fg3);
  margin:14px 0 7px;border-top:1px solid var(--rule);padding-top:9px}
.chev{display:grid;grid-template-columns:1fr 1fr;gap:7px 20px;align-items:start}
.chev .ev{margin-bottom:0;border-left-color:var(--acc)}

/* ---- exhibits ---- */
.exh{margin:12px 0 0}
.exh-lbl{font:700 8.3px/1.3 var(--body);letter-spacing:.16em;text-transform:uppercase;color:var(--fg3);margin-bottom:5px}
.exh-take{font:600 12.8px/1.45 var(--body);color:var(--ink);margin:0 0 9px;max-width:84ch}
.exh-src{font:400 8.3px/1.4 var(--body);color:var(--fg3);margin-top:6px}
.tbl{margin:0}
.tbl table{width:100%;border-collapse:collapse;font:400 10.2px/1.45 var(--body);font-variant-numeric:tabular-nums}
.tbl th{text-align:left;font:700 8px/1.3 var(--body);letter-spacing:.08em;text-transform:uppercase;
  background:var(--acc-t2);color:var(--ink);padding:6px 8px;border-bottom:1.5px solid var(--acc);vertical-align:bottom}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.tbl td.num{text-align:right}
.tbl td:first-child{font-weight:600}
.tbl tbody tr:last-child td{border-bottom:2px solid var(--acc)}
.tbl tfoot td{font:400 8.8px/1.4 var(--body);font-style:italic;color:var(--soft);border:0;padding:6px 0 0}
.pg-matrix .tbl table{font-size:9.1px;line-height:1.38}
.pg-matrix .tbl td{padding:8px 7px}
.pg-matrix .tbl tbody tr:nth-child(even) td{background:var(--card)}
.pg-matrix .exh-take{font-size:13px}
.next-note{margin-top:9px;font:700 9px/1.4 var(--body);color:var(--acc);letter-spacing:.08em;text-transform:uppercase}

/* ---- action plan ---- */
.ap{list-style:none;margin:4px 0 0;padding:0}
.ap li{display:flex;gap:18px;padding:20px 0;border-bottom:1px solid var(--line);align-items:baseline}
.ap li:last-child{border-bottom:0}
.ap li i{font:600 21px/1 var(--disp);font-style:normal;min-width:36px;font-variant-numeric:tabular-nums}
.ap-sec{display:block;font:700 10px/1 var(--body);letter-spacing:.18em;text-transform:uppercase;margin-bottom:6px}
.ap-act{font:400 13.6px/1.58 var(--body);max-width:88ch}

/* ---- methodology + bibliography ---- */
.methods{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--navy);
  padding:13px 16px 12px;margin-bottom:13px}
.m-lbl{font:700 8.8px/1.3 var(--body);letter-spacing:.2em;text-transform:uppercase;color:var(--navy);margin-bottom:7px}
.methods p{margin:0 0 7px;font:400 11px/1.6 var(--body);color:var(--soft)}
.methods p:last-child{margin-bottom:0}
.methods .m-note{color:var(--fg3);font-size:9.3px}
.bib ol{margin:4px 0 0;padding-left:17px;columns:3;column-gap:18px}
.bib li{font:400 9px/1.52 var(--body);color:var(--soft);margin-bottom:6.5px;break-inside:avoid;
  overflow-wrap:anywhere;padding-left:2px}
.bib li::marker{font:700 7.5px/1 var(--body);color:var(--navy)}
.bib a{color:var(--fg3)}

/* ---- appendix A: rejected claims table ---- */
.rjt{width:100%;border-collapse:collapse;font:400 9.2px/1.38 var(--body)}
.rjt th{text-align:left;font:700 7.8px/1.3 var(--body);letter-spacing:.1em;text-transform:uppercase;
  color:var(--fg3);border-bottom:1.5px solid var(--rule);padding:4px 8px 5px 0}
.rjt td{padding:5.5px 8px 5.5px 0;border-bottom:1px solid var(--line);vertical-align:top}
.rj-c{color:var(--soft)}
.rj-t{white-space:nowrap;font:600 8.2px/1.4 var(--body);letter-spacing:.03em;color:var(--fg3);width:120px}
.rj-d{font:400 8.2px/1.4 var(--body);color:var(--fg3);width:150px;overflow-wrap:anywhere}

/* ---- appendix B: evidence ---- */
.app-cols{columns:2;column-gap:20px;column-fill:auto;flex:1;min-height:0;margin-top:4px}
.app-cols.bal{column-fill:balance}
.ev-pair{break-inside:avoid}
.app-cols .ev p{font-size:8.9px}
.app-cols .ev{padding:7px 9px 6px;margin-bottom:6px}
.ev{break-inside:avoid;background:var(--card);padding:8px 10px 7px;margin-bottom:7px;border-left:2px solid var(--rule)}
.ev p{margin:0 0 4px;font:400 9.4px/1.45 var(--body);color:var(--soft)}
.ev-m{display:flex;gap:7px;align-items:center;font:600 7.7px/1.2 var(--body);letter-spacing:.04em;
  text-transform:uppercase;color:var(--fg3);flex-wrap:wrap}
.ev-m a{color:var(--navy);text-transform:none;font-weight:600;letter-spacing:0;font-size:8.3px}
.ev-cor{color:#8a5a00;font-style:italic}
.ev-quote{font-style:italic;font-size:8.6px;color:var(--soft);margin:3px 0 0;border-left:2px solid var(--rule);padding-left:6px;line-height:1.5}
.ev-ct{margin:4px 0 8px;padding:6px 8px;background:#f9f5ef;border-left:3px solid #c04040}
.ev-ct-note{font:700 8.3px/1.4 var(--body);letter-spacing:.06em;text-transform:uppercase;color:#c04040;margin-bottom:5px}
.stance-chip{font:700 8px/1 var(--body);letter-spacing:.06em;text-transform:uppercase;padding:2px 6px;border-radius:3px;margin:4px 0 2px;display:inline-block}
.st-pro{color:#2d6a35;background:#c3d6bb}
.st-con{color:#8c3b36;background:#ddb4ad}
.st-mix{color:#8a5a00;background:#ecd6a4}
.ev-grp{font:700 9.3px/1.3 var(--body);letter-spacing:.12em;text-transform:uppercase;
  margin:0 0 7px;break-inside:avoid;border-bottom:2px solid;padding-bottom:4px}
.ev + .ev-grp{margin-top:12px}
.cls{display:inline-flex;min-width:13px;height:13px;align-items:center;justify-content:center;
  font:700 8px/1 var(--body);border:1px solid var(--navy);color:var(--navy);padding:0 3px;flex:none}
.cls-A{background:var(--navy);color:#fff}
.cls-B{background:#6a7077;color:#fff;border-color:#6a7077}
.cls-C{background:transparent;color:var(--fg3);border-color:var(--rule)}

/* ---- colophon on dark field ---- */
.pg-end{background:var(--navy);color:#fff;padding:17mm 15mm 11mm}
.end-inner{display:flex;flex-direction:column;flex:1;min-height:0}
.end-top{margin:auto 0;padding-bottom:18mm}
.end-eb{color:#9db0d4;letter-spacing:.3em}
.end-h{font:600 30px/1.22 var(--disp);margin:16px 0 0;letter-spacing:-.01em;max-width:26ch}
.end-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;border-top:1px solid rgba(255,255,255,.25);padding-top:16px}
.end-lbl{font:700 8.5px/1 var(--body);letter-spacing:.22em;text-transform:uppercase;color:#9db0d4;margin-bottom:8px}
.end-grid p{margin:0 0 5px;font:400 10.5px/1.5 var(--body);color:#c6d1e6}
.end-grid b{color:#fff;font-weight:600}
.end-note{margin-top:24px;font:400 9.3px/1.55 var(--body);color:#9db0d4;max-width:74ch;
  border-top:1px solid rgba(255,255,255,.25);padding-top:12px}
.end-foot{margin-top:auto}
.end-foot .pf-strip{border-top:1px solid rgba(255,255,255,.3)}
.end-foot .pf-ttl,.end-foot .pf-num{color:#9db0d4}

/* ============ SCREEN: normal website (print does not see this layer) ============ */
.sidenav{display:none}
@media screen{
  html{scroll-behavior:smooth}
  body{background:var(--paper);padding:0}
  /* page → fluid section: height by content, thin separator instead of shadow */
  .page{width:auto;max-width:860px;height:auto;display:block;overflow:visible;
    margin:0 auto;padding:52px 48px 40px;box-shadow:none;border-bottom:1px solid var(--rule);
    scroll-margin-top:12px}
  /* running footer and folio — print furniture; footnotes remain as section block */
  .pf-strip{display:none}
  .page-foot{margin-top:0}
  .pfns{margin-top:26px;padding-top:10px;column-gap:30px}
  .pfn{font-size:11px}
  /* cover → hero header: dark field flows, print TOC replaced by sidenav */
  .pg-cover{padding:0}
  .cv-band{padding:60px 48px 38px}
  .cv-band h1{font-size:32px}
  .cv-dek{font-size:15.5px}
  .cv-body{display:block;padding:30px 48px 6px}
  .cv-toc{display:none}
  .cv-stats{margin-top:0}
  /* screen typography is more spacious; tight/roomy — about print layout, suppressed on screen */
  .pg-head h2{font-size:28px}
  .ch-head h2,.tight .ch-head h2,.roomy .ch-head h2{font-size:30px}
  .narr,.tight .narr,.roomy .narr{font-size:15.5px;line-height:1.72}
  .narr p,.tight .narr p,.roomy .narr p{margin-bottom:14px}
  .narr.cols{columns:1;max-width:74ch}
  .keybox,.tight .keybox,.roomy .keybox{padding:14px 17px 11px;margin-bottom:15px}
  .keys li,.tight .keys li,.roomy .keys li{font-size:13.2px;padding:6px 0 6px 15px}
  .keys li::before,.tight .keys li::before,.roomy .keys li::before{top:13px}
  .pull,.tight .pull,.roomy .pull{font-size:18px;padding:14px 2px;margin:14px 0 6px}
  .xs li div{font-size:15.8px}
  .ap-act{font-size:15px}
  .tbl table,.tight .tbl table{font-size:12.4px;line-height:1.55}
  .pg-matrix,.pg-meth,.pg-app{max-width:1320px}
  .pg-matrix .tbl table,.pg-matrix.tight .tbl table{font-size:13.8px;line-height:1.55}
  .pg-matrix .tbl td{padding:13px 11px}
  .pg-matrix .tbl th{font-size:10.5px}
  .pg-matrix .exh-take{font-size:15px}
  .next-note{display:none}
  .pg-meth .bib ol{columns:3;column-gap:34px}
  .pg-meth .bib li{font-size:11.5px;line-height:1.58;margin-bottom:9px}
  .pg-meth .methods p{font-size:14px;line-height:1.65}
  /* appendices on screen: readable size */
  .app-cols .ev p,.ev p{font-size:13.5px;line-height:1.6}
  .app-cols .ev{padding:12px 15px 10px;margin-bottom:11px}
  .ev-m,.app-cols .ev-m{font-size:10.5px}
  .ev-grp{font-size:11.5px}
  .rjt,.rjt td{font-size:13px;line-height:1.55}
  .rjt td{padding:9px 12px 9px 0}
  .rjt th{font-size:9.5px}
  .ph-sub{font-size:13.5px}
  /* appendices: columns balance by content, not A4 height */
  .app-cols{column-fill:balance}
  /* colophon */
  .pg-end{padding:56px 48px 44px}
  .end-top{margin:0;padding-bottom:36px}
}
/* sticky sidebar navigation — wide screen */
@media screen and (min-width:1100px){
  .sidenav{display:block;position:fixed;top:48px;left:max(16px,calc(50% - 760px));width:224px;
    max-height:calc(100vh - 96px);overflow:auto;padding-right:8px}
  .page{margin-left:max(260px,calc(50% - 516px));margin-right:auto}
  .sn-home{display:block;font:700 9px/1.5 var(--body);letter-spacing:.22em;text-transform:uppercase;
    color:var(--navy);border-bottom:2px solid var(--navy);padding-bottom:9px;margin-bottom:14px}
  .sn-lbl{font:700 8.5px/1 var(--body);letter-spacing:.24em;text-transform:uppercase;
    color:var(--fg3);margin-bottom:8px}
  .sidenav ol{list-style:none;margin:0;padding:0}
  .sidenav li a{display:flex;gap:10px;align-items:baseline;padding:5.5px 0;
    font:500 11.5px/1.4 var(--body);color:var(--soft);border-bottom:1px solid var(--line)}
  .sidenav li:last-child a{border-bottom:0}
  .sidenav li a:hover .sn-t{color:var(--ink)}
  .sn-n{font:700 9px/1.4 var(--body);min-width:20px;flex:none;letter-spacing:.04em;
    font-variant-numeric:tabular-nums}
  .sn-t{flex:1}
  .sidenav li a.on{border-bottom-color:var(--rule)}
  .sidenav li a.on .sn-t{color:var(--ink);font-weight:700}
}

/* very wide screen: footnotes go to right column (notes rail) */
@media screen and (min-width:1420px){
  .page{display:grid;grid-template-columns:minmax(0,820px) 270px;column-gap:46px;
    max-width:1136px;align-items:start}
  .page>*{grid-column:1}
  .page>.page-foot{grid-column:2;grid-row:1 / span 60;align-self:start;position:sticky;top:36px;margin-top:0}
  .pfns{margin-top:0;padding-top:0;border-top:0;columns:1}
  .pfn{font-size:11px;line-height:1.5;margin-bottom:7px}
  .pg-cover,.pg-end,.pg-matrix,.pg-meth,.pg-app{display:block}
  .pg-matrix,.pg-meth,.pg-app{max-width:1320px}
}
/* mobile: no navigation, content full width */
@media screen and (max-width:720px){
  .page{padding:36px 20px 32px}
  .cv-band{padding:44px 20px 28px}
  .cv-band h1{font-size:27px}
  .cv-body{padding:24px 20px 4px}
  .pg-end{padding:44px 20px 36px}
  .keys{columns:1}
  .cs-grid{grid-template-columns:repeat(2,1fr)}
  .end-grid{grid-template-columns:1fr}
  .bib ol{columns:1}
  .app-cols{columns:1}
  .pfns{columns:1}
  .chev{grid-template-columns:1fr}
  .tbl{overflow-x:auto}
}
""" + ACC_CSS

OUT = ('<!doctype html>\n<html lang="' + esc(LANG) + '">\n<head>\n<meta charset="utf-8">\n'
       '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
       f'<title>{esc(page_title)}</title>\n'
       '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
       '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
       '<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&family=Source+Sans+3:ital,wght@0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
       f'<style>{CSS}</style>\n</head>\n<body>\n'
       + sidenav_html + "\n"
       + "\n".join(pages_html) + "\n" + SIDENAV_JS + "\n</body>\n</html>")

(ROOT / "reports").mkdir(exist_ok=True)
_out_path = (cfg("out") or f"reports/REPORT-{TOPIC}.html")
# paged renderer writes alongside, not overwriting the main and consulting reports
_out_path = _out_path.replace(".html", "-paged.html")
dst = ROOT / _out_path
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(OUT, encoding="utf-8")
print(f"done: {dst} ({len(OUT) // 1024} KB, {total_pages} pages, {n_facts} facts, "
      f"{n_rev} rejected, {len(FOOTNOTES)} footnotes)")
print(f"  pages: cover 1 · exec 2 · chapters 3–{2 + len(chapters)}"
      + (f" · matrix {matrix_page_no}" if matrix_page_no else "")
      + f" · appendix A from {appB_page_no} · appendix B from {appA_page_no}")
if PROSE_WARN:
    print(f"⚠ prose exceeds limit in {len(PROSE_WARN)} sections (teaching format: limit ≤16 sentences / 2000 chars — this guards against a wall of text):")
    print("\n".join(PROSE_WARN))
