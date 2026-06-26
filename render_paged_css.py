#!/usr/bin/env python3
"""Static stylesheet for render_paged.py (paged/print report).

Extracted verbatim from render_paged.py; the renderer appends the
computed per-accent ACC_CSS at use site (CSS = BASE_CSS + ACC_CSS).
"""

BASE_CSS = """
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
"""
