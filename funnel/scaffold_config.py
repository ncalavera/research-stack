#!/usr/bin/env python3
"""Minimal layout config for a new topic (chain safety net).

render_final.py degrades without a config, but then the report has an empty title and one section.
This script assembles a valid reports/<topic>.config.json from the pool: sections, default
title, footer. The Opus step of the /research chain will then rewrite the texts and add narratives —
scaffold does NOT overwrite an existing config (to avoid erasing custom layout).

Usage: python3 scaffold_config.py <topic> ["Report Title"]
"""
import sys, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent  # repository root (script lives in funnel/)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P
topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
title = sys.argv[2] if len(sys.argv) > 2 else f"Verified Report — {topic}"

cfg_path = P.config(topic)
if cfg_path.exists():
    print(f"config already exists ({cfg_path.name}) — leaving untouched")
    sys.exit(0)

pool = json.loads(P.pool(topic).read_text("utf-8"))
sections, seen = [], set()
for f in pool["facts"]:
    s = f.get("section") or "Other"
    if s not in seen:
        seen.add(s)
        sections.append(s)

cfg = {
    "_meta": "Auto-skeleton (scaffold_config.py). Opus step /research will rewrite texts and add narratives_file.",
    "lang": "en",
    "page_title": title,
    "kicker": "Verified Report · fact-check funnel",
    "title_html": title,
    "dek": "What on this topic is genuinely confirmed by a live primary source, not just stated confidently.",
    "intro": "",
    "show_personal_dek": False,
    "tldr_title": "If you read only this",
    "narratives_file": f"topics/{topic}/narratives.json",
    "section_order": sections,
    "footer_methods": "Engines: Exa research/answer, OpenAI o4-mini deep research, Perplexity sonar and deep, Claude deep research. Each fact passed fact-check gates: confirmed by a live class A/B source. The number next to a fact is how many engines found it.",
    "footer_note": f"Assembled by the research-stack fact-check funnel. Topic: {topic}.",
    "out": f"reports/REPORT-{topic}.html",
}
P.topic_dir(topic).mkdir(parents=True, exist_ok=True)
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
print(f"→ topics/{topic}/config.json  ({len(sections)} sections: {', '.join(sections)})")
