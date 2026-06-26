#!/usr/bin/env python3
"""Shared rendering helpers used by both render_paged.py and render_final.py.

Pure, self-contained building blocks (no module-level data state):
  - esc / domain      — HTML escaping and URL → bare domain
  - _num / _pos       — numeric label and scale-position helpers
  - _viz_* / _VIZ     — mini-chart builders for narratives._section_viz

Each renderer keeps its own section_viz_html / src_link etc. that close over
its module-level data (SECTION_VIZ, SRC, …); only the data-free pieces live here.
"""
import html


def esc(t):
    return html.escape(str(t))


def domain(url):
    try:
        return url.split("/")[2].replace("www.", "")
    except Exception:
        return url


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
