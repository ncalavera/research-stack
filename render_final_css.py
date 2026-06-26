#!/usr/bin/env python3
"""Static stylesheet for render_final.py (web/final report).

Extracted verbatim from the OUT template in render_final.py (braces un-doubled
back to plain CSS); spliced in at use site between <style> and </style>.
"""

STYLE_CSS = """:root{
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
}
@media(prefers-color-scheme:dark){
  :root{
    --paper:#1a1816; --card:#221e19; --ink:#ece7dd; --soft:#a39c8e; --fg3:#9a9286;
    --line:#2c2820; --rule:#3a352c;
    --clay:#e08a5c; --clay-deep:#e8a079; --clay-tint:#2e211a;
    --teal:#5fa8a2; --teal-tint:#16302e;
    --zg:#7fb07f; --zg-b:#33452f;
    --zw:#d6a84e; --zw-b:#463a1e;
    --zr:#d97169; --zr-b:#4a2925;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);
  font:400 15px/1.56 var(--body);
  font-feature-settings:"ss01";-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{max-width:820px;margin:0 auto;padding:clamp(32px,5vw,56px) 28px 80px}
::selection{background:var(--ink);color:var(--paper)}
a{color:inherit}
*{scroll-margin-top:24px}

/* ---- sidebar navigation (wide screen only, no JS) ---- */
.sidenav{display:none}
@media(min-width:1280px){
  .sidenav{display:block;position:fixed;top:56px;left:max(20px,calc(50% - 620px));width:186px;
    max-height:calc(100vh - 96px);overflow:auto}
  .sidenav .sn-lbl{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;
    color:var(--soft);margin:0 0 12px}
  .sidenav ol{list-style:none;margin:0;padding:0}
  .sidenav li a{display:flex;gap:9px;align-items:baseline;padding:5px 0;
    font:500 13px/1.32 var(--body);color:var(--soft);text-decoration:none;transition:color .12s}
  .sidenav li a:hover{color:var(--ink)}
  .sidenav .sn-n{font:600 11px/1.4 var(--mono);color:var(--fg3);min-width:18px;flex:none}
}

/* ---- table of contents page (print/PDF only) ---- */
.toc-print{display:none}

/* Typographic scale — 6 steps across the page: 11 / 13 / 15 / 19 / 24 / 40.
   11 — small detail (mono labels, badges, axes, table headers); 13 — numbers/values;
   15 — body text and bullets; 19 — dek and large scale numbers; 24 — H2; 40 — H1. */

/* ---- masthead ---- */
.kicker{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);margin:0 0 20px}
h1{font:800 clamp(24px,7vw,40px)/0.98 var(--disp);letter-spacing:-.035em;margin:0 0 14px}
.dek{font:400 19px/1.34 var(--body);color:var(--soft);margin:0 0 4px;max-width:34ch;letter-spacing:-.01em}
.dek.personal{color:var(--ink);font-size:15px;line-height:1.5;max-width:54ch;margin-top:16px}
.byline{font:500 11px/1.5 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--soft);
  border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:15px 0;margin:30px 0 0;
  display:flex;flex-wrap:wrap;gap:8px 36px;font-variant-numeric:tabular-nums}
.byline b{color:var(--ink);font-weight:600;font-size:13px}

/* ---- intro + single drop cap ---- */
.intro{font-size:15px;line-height:1.54;margin:32px 0 8px;max-width:68ch}
.intro::first-letter{font:800 4.1em/.72 var(--disp);float:left;color:var(--ink);margin:9px 12px 0 0}

/* ---- In brief — numbered register ---- */
.tldr{margin:30px 0 10px;border-top:2px solid var(--ink);padding-top:4px}
.tldr .lbl{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);display:block;margin:14px 0 2px}
.tldr h3{font:700 24px/1.1 var(--disp);letter-spacing:-.025em;margin:2px 0 10px}
.tldr ol{margin:0;padding:0;list-style:none;counter-reset:tl}
.tldr li{display:grid;grid-template-columns:26px 1fr;gap:5px 12px;align-items:baseline;
  padding:10px 0;border-top:1px solid var(--line);counter-increment:tl}
.tldr li:first-child{border-top:0}
.tldr li::before{content:counter(tl,decimal-leading-zero);font:600 11px/1.7 var(--mono);color:var(--fg3)}
.tldr li span{font-size:15px;line-height:1.42}

/* ---- sections ---- */
.sec{margin:52px 0 0}
.sec-head{display:flex;align-items:baseline;gap:12px;border-bottom:1px solid var(--rule);padding-bottom:10px;margin-bottom:16px}
.sec-num{font:500 11px/1 var(--mono);color:var(--fg3)}
.sec-head h2{font:700 clamp(19px,3.6vw,24px)/1.06 var(--disp);letter-spacing:-.03em;margin:0;flex:1}
.sec-count{font:500 11px/1 var(--mono);color:var(--fg3);text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}

/* ---- narrative ---- */
.narr{font-size:15px;line-height:1.56;max-width:68ch;margin:0 0 4px}
.narr p{margin:0 0 13px}
.narr a{color:var(--teal);text-decoration:underline;text-decoration-color:var(--teal);text-underline-offset:3px;text-decoration-thickness:1px;transition:text-decoration-thickness .15s}
.narr a:hover{text-decoration-thickness:2px}

/* ---- so what — marginalia ---- */
.sowhat{margin:20px 0 6px;padding:0 0 2px 20px;border-left:2px solid var(--ink);max-width:62ch}
.sw-lbl{font:700 24px/1 var(--hand);color:var(--soft);display:inline-block;transform:rotate(-2.5deg);margin:0 0 3px}
.sowhat p{margin:0;font:500 15px/1.5 var(--body);color:var(--ink)}

/* ---- key bullets ---- */
.keys{max-width:68ch;margin:15px 0 4px;padding:0;list-style:none}
.keys li{position:relative;padding:6px 0 6px 20px;font-size:15px;line-height:1.5;border-bottom:1px solid var(--line)}
.keys li:last-child{border-bottom:0}
.keys li::before{content:"";position:absolute;left:2px;top:13px;width:5px;height:5px;background:var(--ink)}

/* ---- table ---- */
.tbl{margin:22px 0 6px;max-width:760px}
.tbl figcaption{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--soft);margin:0 0 10px}
.tbl table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
.tbl th{text-align:left;font:600 11px/1.3 var(--mono);letter-spacing:.05em;text-transform:uppercase;
  color:var(--soft);padding:0 14px 8px 0;border-bottom:1.5px solid var(--ink);vertical-align:bottom}
.tbl td{padding:9px 14px 9px 0;border-bottom:1px solid var(--line);vertical-align:top;line-height:1.4}
.tbl td:first-child{font-weight:600;color:var(--ink);white-space:nowrap}
.tbl tbody tr:last-child td{border-bottom:1.5px solid var(--rule)}
.tbl tfoot td{font:500 13px/1.4 var(--body);font-style:italic;color:var(--soft);
  padding-top:10px;border:0}

/* ---- dashboard (Editorial Warmth): hero + zone strips ---- */
.dash{margin:34px 0 8px}
.dash-title{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);
  margin:0 0 16px;display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.dash-title em{font-style:normal;color:var(--fg3)}

/* hero: gauge + track */
.hero{display:flex;flex-wrap:wrap;gap:18px;margin:0 0 6px}
.hero>.hcard{flex:1 1 320px}
.hero>.dial-wrap{flex:0 0 204px}
.hcard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;
  box-shadow:0 1px 3px rgba(26,24,22,.05)}
.hcard .hl{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--soft);margin:0 0 14px}
/* ---- number cards (top infographic + stat-hero dashboard) ---- */
.infographic{margin:30px 0 8px}
.ig-title{font:600 11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);margin:0 0 16px}
.infographic figcaption{margin:14px 0 0;font:400 13px/1.5 var(--body);color:var(--fg3);max-width:62ch}
.statgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.infographic>.statgrid .stat{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:18px 18px 16px;box-shadow:0 1px 3px rgba(26,24,22,.05)}
.stat{display:flex;flex-direction:column;gap:3px}
.stat .sv{font:700 30px/1 var(--disp);letter-spacing:-.02em;color:var(--ink)}
.stat .su{font:600 11px/1.2 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--fg3)}
.stat .sl{margin-top:6px;font:400 13px/1.4 var(--body);color:var(--soft)}

/* gauge (zone reference, no invented needle) */
.dial-wrap{display:flex;flex-direction:column;align-items:center}
.dial{position:relative;width:150px;aspect-ratio:1;border-radius:50%;margin:2px 0 14px;
  background:conic-gradient(from 135deg,
    var(--zr-b) 0deg 89deg, var(--zw-b) 89deg 181deg, var(--zg) 181deg 270deg, transparent 270deg 360deg)}
.dial::after{content:"";position:absolute;inset:19px;border-radius:50%;background:var(--card);box-shadow:inset 0 0 0 1px var(--line)}
.dial .read{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:2}
.dial .rv{font:800 24px/1 var(--disp);letter-spacing:-.03em;color:var(--zg)}
.dial .rt{font:600 11px/1.3 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--soft);margin-top:5px}
.dial-zones{display:flex;gap:11px;font:500 11px/1 var(--mono);letter-spacing:.02em}
.dial-zones span{display:inline-flex;align-items:center;gap:4px;color:var(--fg3)}
.dial-zones i{width:8px;height:8px;border-radius:2px}

/* progress track: from → to */
.wtop{display:flex;align-items:baseline;gap:8px;margin:0 0 22px}
.wtop .wnow{font:800 clamp(24px,5vw,40px)/.9 var(--disp);letter-spacing:-.035em;color:var(--clay);font-variant-numeric:tabular-nums}
.wtop .warr{font:600 19px/1 var(--mono);color:var(--fg3)}
.wtop .wgoal{font:800 24px/.9 var(--disp);letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}
.wtop .wun{font:600 13px/1 var(--mono);color:var(--soft);align-self:center}
.wtop .wdelta{margin-left:auto;align-self:center;font:600 11px/1 var(--mono);color:var(--clay-deep);
  border:1px solid var(--clay);border-radius:4px;padding:4px 8px}
.wtrack{position:relative;height:8px;border-radius:5px;background:var(--line)}
.wtrack .gap{position:absolute;top:0;bottom:0;border-radius:5px;
  background:repeating-linear-gradient(90deg,var(--clay-tint) 0 6px,transparent 6px 10px);box-shadow:inset 0 0 0 1px var(--clay-tint)}
.wtrack .goal{position:absolute;top:-7px;width:2px;height:22px;background:var(--ink)}
.wtrack .now{position:absolute;top:50%;width:14px;height:14px;border-radius:50%;background:var(--clay);
  transform:translate(-50%,-50%);box-shadow:0 0 0 3px var(--card)}
.wcap{position:relative;height:14px;margin-top:11px}
.wcap span{position:absolute;transform:translateX(-50%);font:600 11px/1 var(--mono);letter-spacing:.04em;
  text-transform:uppercase;white-space:nowrap}
.wcap .c-now{color:var(--clay-deep)} .wcap .c-goal{color:var(--ink)}
.wends{display:flex;justify-content:space-between;font:500 11px/1 var(--mono);color:var(--fg3);margin-top:7px}
.wmeta{margin:15px 0 0;padding-top:13px;border-top:1px solid var(--line);font:400 13px/1.5 var(--body);color:var(--soft)}
.wmeta b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}

/* zone strips per metric */
.strips{margin:14px 0 0;border-top:1px solid var(--rule)}
.strip{display:grid;grid-template-columns:124px 1fr;gap:18px;align-items:center;
  padding:15px 0;border-bottom:1px solid var(--line)}
.strip:last-child{border-bottom:0}
.strip-v{font:800 19px/1 var(--disp);letter-spacing:-.02em;color:var(--ink);font-variant-numeric:tabular-nums}
.strip-l{display:block;font:600 11px/1.3 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--soft);margin-top:4px}
.strip-bar{position:relative;height:9px;border-radius:5px}
.strip-mark{position:absolute;top:-3px;height:15px;width:2px;background:var(--clay);border-radius:1px}
.strip-mark::after{content:"";position:absolute;top:-4px;left:-3px;width:8px;height:8px;border-radius:50%;background:var(--clay)}
.strip-mband{position:absolute;top:-2px;bottom:-2px;border:1.5px solid var(--clay);border-radius:4px}
.strip-ax{display:flex;justify-content:space-between;font:500 11px/1 var(--mono);color:var(--fg3);margin-top:6px}
.strip-note{font:400 13px/1.4 var(--body);font-style:italic;color:var(--fg3);margin-top:4px}

/* fact-check funnel — proportional bar */
.funnel{margin:18px 0 0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px 15px}
.funnel-l{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--soft);margin:0 0 11px}
.funnel-bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--line)}
.funnel-bar .f-ok{background:var(--teal)} .funnel-bar .f-rev{background:var(--rule)}
.funnel-leg{display:flex;justify-content:space-between;gap:10px;margin-top:10px;
  font:500 11px/1.4 var(--mono);color:var(--soft);flex-wrap:wrap}
.funnel-leg b{color:var(--ink)} .funnel-leg .t b{color:var(--teal)}
.dash-cap{margin:17px 0 0;font:400 13px/1.5 var(--body);color:var(--fg3);max-width:62ch}
@media(max-width:560px){
  .hero{grid-template-columns:1fr}
  .strip{grid-template-columns:100px 1fr;gap:13px}
}

/* ---- mini-charts in sections ---- */
.svz{margin:22px 0 6px;max-width:760px}
.svz figcaption{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--soft);margin:0 0 12px}
.svz-note{margin:11px 0 0;font:400 13px/1.45 var(--body);font-style:italic;color:var(--fg3)}
/* sleep phase stack */
.stk-bar{display:flex;height:34px;border-radius:7px;overflow:hidden;border:1px solid var(--line)}
.stk-bar span{display:block;min-width:2px}
.stk-leg{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:11px;font:500 11px/1.4 var(--mono);color:var(--soft)}
.stk-leg span{display:inline-flex;align-items:center;gap:6px}
.stk-leg i{width:9px;height:9px;border-radius:2px}
.stk-leg b{color:var(--ink);font-weight:600}
/* training volume dot grid */
.dots{display:flex;flex-wrap:wrap;gap:5px}
.dots i{width:15px;height:15px;border-radius:3px;border:1px solid var(--rule)}
.dots i.in{background:var(--zg);border-color:var(--zg)}
/* daily protein timeline */
.tl-bar{position:relative;height:38px;background:var(--card);border:1px solid var(--line);border-radius:8px}
.tl-win{position:absolute;top:5px;bottom:5px;border-radius:5px;background:var(--clay-tint);border:1px dashed var(--clay)}
.tl-dose{position:absolute;top:7px;bottom:7px;width:34px;transform:translateX(-50%);border-radius:4px;
  background:var(--zg);display:flex;align-items:center;justify-content:center}
.tl-dose b{font:700 11px/1 var(--mono);color:var(--paper)}
.tl-hours{display:flex;justify-content:space-between;margin-top:7px;font:500 11px/1 var(--mono);color:var(--fg3)}
/* category bands (body fat %) */
.bd-bar{position:relative;height:30px;border-radius:7px;background:var(--line)}
.bd-seg{position:absolute;top:0;bottom:0;display:flex;align-items:center;justify-content:center;overflow:hidden}
.bd-seg em{font:600 11px/1 var(--mono);font-style:normal;letter-spacing:.04em;text-transform:uppercase;
  color:var(--ink);opacity:.7;padding:0 4px;white-space:nowrap}
.bd-target{position:absolute;top:-4px;bottom:-4px;border:2px solid var(--clay);border-radius:6px;pointer-events:none}
.bd-ax{display:flex;justify-content:space-between;margin-top:7px;font:500 11px/1 var(--mono);color:var(--fg3)}

/* comparison bars (direct labeling, zero baseline) */
.br{display:flex;flex-direction:column;gap:9px}
.br-row{display:grid;grid-template-columns:minmax(90px,30%) 1fr auto;align-items:center;gap:12px}
.br-lbl{font:500 13px/1.3 var(--body);color:var(--soft);text-align:right}
.br-track{height:18px;background:var(--line);border-radius:4px;overflow:hidden}
.br-fill{display:block;height:100%;border-radius:4px}
.br-val{font:600 13px/1 var(--mono);color:var(--ink);min-width:34px}
/* part-of-whole ring */
.dn{display:flex;align-items:center;gap:22px;flex-wrap:wrap}
.dn-svg{width:96px;height:96px;flex:none}
.dn-leg{display:flex;flex-direction:column;gap:8px;font:500 13px/1.3 var(--body);color:var(--soft)}
.dn-leg span{display:inline-flex;align-items:center;gap:8px}
.dn-leg i{width:11px;height:11px;border-radius:3px;flex:none}
.dn-leg b{color:var(--ink);font-weight:600}
/* trend line */
.ln-svg{width:100%;height:90px;display:block;overflow:visible}
.ln-ax{display:flex;justify-content:space-between;margin-top:7px;font:500 11px/1 var(--mono);color:var(--fg3)}
.ln-ends{display:flex;justify-content:space-between;margin-top:3px;font:500 10px/1 var(--mono);color:var(--fg3);opacity:.7}

/* ---- action plan ---- */
.plan{margin:56px 0 0}
.plan .ap{margin:8px 0 0;padding:0;list-style:none}
.plan .ap li{display:grid;grid-template-columns:22px 1fr;gap:2px 12px;
  padding:11px 0;border-bottom:1px solid var(--line)}
.plan .ap li::before{content:"☐";grid-column:1;grid-row:1/3;font:400 15px/1.3 var(--mono);color:var(--soft)}
.ap-sec{grid-column:2;font:600 11px/1.4 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--fg3)}
.ap-act{grid-column:2;font:500 15px/1.45 var(--body);color:var(--ink)}

/* ---- evidence (collapsed) ---- */
.evidence{margin:16px 0 0;max-width:62ch}
.evidence>summary{list-style:none;cursor:pointer;font:600 11px/1 var(--mono);letter-spacing:.08em;
  text-transform:uppercase;color:var(--soft);padding:11px 0;border-top:1px solid var(--line);
  display:flex;align-items:center;gap:8px;font-variant-numeric:tabular-nums}
.evidence>summary::-webkit-details-marker{display:none}
.evidence>summary::before{content:"+";font:500 13px/1 var(--mono);width:10px}
.evidence[open]>summary::before{content:"–"}

/* ---- fact ---- */
.fact{padding:13px 0;border-bottom:1px solid var(--line)}
.claim{margin:0 0 8px;font:400 15px/1.5 var(--body)}
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font:500 11px/1 var(--mono);color:var(--soft)}
.cls{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 4px;
  border-radius:4px;font:600 11px/1 var(--mono);border:1.5px solid var(--ink);color:var(--ink)}
.cls-A{background:var(--ink);color:var(--paper)}
.cls-B{background:var(--soft);color:var(--paper);border-color:var(--soft)}
.cls-C{background:transparent;color:var(--soft);border-color:var(--rule)}
.conf{letter-spacing:.06em;color:var(--ink);font-size:11px}
.engs{display:inline-flex;flex-wrap:wrap;gap:5px}
.eng{color:var(--fg3);border:1px solid var(--line);border-radius:4px;padding:2px 7px;font:500 11px/1 var(--mono)}
.srcs{display:inline-flex;flex-wrap:wrap;gap:4px 12px;margin-left:auto}
.src{color:var(--teal);text-decoration:underline;text-decoration-color:var(--teal);
  text-decoration-thickness:1px;text-underline-offset:2px;
  font:500 13px/1.4 var(--mono);white-space:nowrap}
.src:hover{text-decoration-thickness:2px}
.note{margin:8px 0 0;font:400 13px/1.45 var(--body);font-style:italic;color:var(--fg3)}
.corrected-badge{margin:8px 0 0;font:500 13px/1.45 var(--mono);color:var(--zw);border-left:2px solid var(--zw-b);padding-left:8px}

/* ---- verbatim source excerpt ---- */
.src-quote{margin:8px 0 0;font:400 13px/1.45 var(--body);color:var(--fg3);border-left:2px solid var(--rule);padding-left:8px}
.src-quote summary{cursor:pointer;font:600 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--soft);list-style:none;display:inline-flex;align-items:center;gap:5px}
.src-quote summary::-webkit-details-marker{display:none}
.src-quote summary::before{content:"+";font:500 11px/1 var(--mono)}
.src-quote[open] summary::before{content:"–"}
.src-quote[open]{padding-bottom:4px}

/* ---- source disagreements ---- */
.contradiction{margin:16px 0;background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 18px 16px}
.ct-head{font:600 11px/1.4 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--zr);margin:0 0 6px}
.ct-note{font:400 13px/1.45 var(--body);font-style:italic;color:var(--fg3);margin:0 0 10px}
.ct-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0}
.ct-grid .fact{border-bottom:1px solid var(--line);padding:10px 0}
.ct-grid .fact:last-child{border-bottom:0}
@media(min-width:600px){
  .ct-grid{gap:0 18px}
  .ct-grid .fact{border-bottom:1px solid var(--line);border-right:1px solid var(--line);padding:10px 14px 10px 0}
  .ct-grid .fact:last-child{border-right:0}
}

/* ---- stance chips (contradiction groups) ---- */
.stance-chip{font:600 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;padding:3px 8px;border-radius:4px;margin:8px 0 -4px;display:inline-block}
.st-pro{color:var(--zg);background:var(--zg-b)}
.st-con{color:var(--zr);background:var(--zr-b)}
.st-mix{color:var(--zw);background:var(--zw-b)}

/* ---- footnotes ---- */
.fnref{font:600 10px/1 var(--mono);vertical-align:super;letter-spacing:.02em}
.fnref a{color:var(--teal);text-decoration:none}
.fnref a:hover{text-decoration:underline}
.fnotes{margin:14px 0 4px;max-width:68ch;border-top:1px solid var(--line);padding-top:8px}
.fnotes .fn-lbl{font:600 10px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--soft);display:block;margin-bottom:4px}
.fnotes ol{margin:0;padding-left:18px}
.fnotes li{font-size:11.5px;line-height:1.5;color:var(--soft);margin:2px 0;overflow-wrap:anywhere}
.fnotes a{color:var(--teal);text-decoration:none}
.fnotes a:hover{text-decoration:underline}

/* ---- To review ---- */
.review{margin:64px 0 0;border:1px solid var(--rule);border-radius:12px;background:var(--card);
  padding:4px 26px 10px;box-shadow:0 1px 3px rgba(26,24,22,.04)}
.review[open]{padding-bottom:26px}
.review>summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:baseline;
  gap:6px 14px;padding:18px 0 14px}
.review>summary::-webkit-details-marker{display:none}
.review>summary::before{content:"+";font:500 15px/1 var(--mono);color:var(--soft);margin-right:2px}
.review[open]>summary::before{content:"–"}
.rsum-h2{font:700 clamp(19px,3.2vw,24px)/1.06 var(--disp);letter-spacing:-.02em}
.rsum-n{font:500 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--fg3)}
.review>.sub{font-size:15px;color:var(--soft);margin:0 0 16px;max-width:56ch;line-height:1.55}
.rfact{padding:14px 0;border-top:1px solid var(--line)}
.rfact .claim{font-size:15px;margin-bottom:7px}
.rlabel{border:1px solid var(--rule);color:var(--soft);border-radius:4px;padding:2px 7px;
  font:600 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase}
.rwhy{margin:7px 0 0;font:400 13px/1.45 var(--body);font-style:italic;color:var(--fg3)}
.nolink{color:var(--fg3);font:500 11px/1 var(--mono)}

/* ---- colophon ---- */
.foot{margin:64px 0 0;padding-top:20px;border-top:2px solid var(--ink);
  font:400 13px/1.55 var(--body);color:var(--soft);max-width:62ch}
.foot .legend{display:flex;flex-wrap:wrap;gap:8px 18px;margin:14px 0;font:500 11px/1 var(--mono)}
.foot .legend span{display:inline-flex;align-items:center;gap:7px}
.foot b{color:var(--ink);font-weight:600}

@media print{
  @page{margin:18mm 16mm}
  body{background:#fff;color:#111;font-size:10.5pt;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .wrap{max-width:none;padding:0}
  .sidenav{display:none}
  a{color:var(--teal)}
  .src,.narr a{text-decoration-color:var(--teal)}
  /* table of contents page: its own page after the cover */
  .toc-print{display:block;break-before:page;break-after:page;padding-top:6mm}
  .toc-print .kicker{margin:0 0 18px}
  .toc-print ol{list-style:none;margin:0;padding:0;counter-reset:tp}
  .toc-print li a{display:flex;align-items:baseline;gap:14px;padding:10px 0;
    border-bottom:1px solid var(--line);color:#111;text-decoration:none}
  .toc-print .tp-n{font:600 13px/1.4 var(--mono);color:var(--soft);min-width:26px}
  .toc-print .tp-t{font:600 15px/1.3 var(--disp)}
  /* expand collapsed sections — in PDF evidence and "To review" must be visible */
  details>summary{display:none}
  .evidence,.review{display:block}
  .evidence>:not(summary),.review>:not(summary){display:block !important}
  .review{background:#fff;border:1px solid #bbb;box-shadow:none;padding:0;margin-top:32px}
  .hcard,.funnel{box-shadow:none}
  /* avoid breaking semantic blocks across pages */
  .sec,.strip,.fact,.rfact,.tbl,.svz,.hero,.plan .ap li{break-inside:avoid}
  .sec-head h2,.tldr h3{break-after:avoid}
}
@media(max-width:560px){
  .wrap{padding:32px 18px 64px}
  .srcs{margin-left:0;width:100%}
}"""
