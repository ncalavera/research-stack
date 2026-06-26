#!/usr/bin/env python3
"""term_gate — hard gate: "every piece of jargon is explained at first mention".

A non-technical reader of the report does not know industry terms. The clarity
standard requires: the first mention of any jargon carries a mini-explanation
right next to it. This gate checks that requirement objectively — not on the
editor's honour.

How it works:
- collects the prose in READING ORDER (_tldr → _so_what → _action_plan → sections
  by section_order from config), as the reader sees it;
- strips citation links (<a …>…</a>) and html tags, so that empty citation
  parens "()" do not count as an explanation;
- for each term in the dictionary finds the FIRST occurrence and checks whether a
  gloss marker is adjacent: a paren with a letter inside, an em dash "—",
  "то есть"/"that is", guillemets «…».
- no gloss at the first occurrence → the gate fails (exit 1) and prints the term
  and its location.

Run: python3 funnel/term_gate.py <topic>
Extend the dictionary via the TERMS list below; self-evident proper names are not
gated — only mechanism terms.
"""
import json
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

# Jargon that MUST be explained at first mention. Each entry is
# (label, regex of first occurrence). Regexes are case-insensitive, Cyrillic-aware.
TERMS = [
    ("HARO", r"\bHARO\b"),
    ("GEO", r"\bGEO\b"),
    ("DA / domain authority", r"\bDA\b"),
    ("YMYL", r"\bYMYL\b"),
    ("PageRank", r"\bPageRank\b"),
    ("rel=nofollow", r"rel=.{0,2}nofollow"),
    ("rel=sponsored", r"rel=.{0,2}sponsored"),
    ("link-scheme", r"link-scheme"),
    ("niche-edit", r"niche-?edit"),
    ("масс-гест", r"масс-гест"),
    ("анкор", r"\bанкор"),
    ("сниппет", r"сниппет"),
    ("бай-лайн", r"бай-?лайн"),
    ("PR-синдикация", r"PR-синдикаци"),
    ("llms.txt", r"llms\.txt"),
    ("schema / structured data", r"\bschema\b"),
    ("AI Overviews", r"AI Overviews"),
    ("листикл", r"листикл"),
    ("питч", r"\bпитч"),
    ("пиллар", r"\bпиллар"),
    ("контент-магнит", r"контент-магнит"),
    ("ссылающийся домен", r"ссылающ\w+ домен"),
    ("медиапак", r"медиапак"),
    ("лонгрид", r"лонгрид"),
    ("карго-культ", r"карго-культ"),
    ("дата-отчёт/дата-исследование", r"дата-(отчёт|исследован)"),
]

# A gloss counts only if it sits IMMEDIATELY next to the term — otherwise a stray
# dash from a neighbouring phrase would falsely pass as an explanation.
# After the term (allowing a case ending ≤4 letters): paren-with-letter, dash, "то есть".
GLOSS_AFTER = re.compile(r"^[\w\"»'\].]{0,5}[\s,]*(\([^)]*[A-Za-zА-Яа-яЁё][^)]*\)|[—–]\s|«[^»]+»|то есть|т\.е\.|that is|i\.e\.)")
# …or IMMEDIATELY before the term sits an opening gloss ("service X — HARO", "(DA …").
GLOSS_BEFORE = re.compile(r"[(—–]\s*\w{0,4}$")
GAP_AFTER = 200  # how many chars after the term we allow for the gloss


def reading_order_text(topic: str) -> str:
    narr = json.loads(P.narratives(topic).read_text("utf-8"))
    order = []
    cfg_path = P.config(topic)
    if cfg_path.exists():
        order = json.loads(cfg_path.read_text("utf-8")).get("section_order", [])
    parts = []
    for t in narr.get("_tldr", []):
        if isinstance(t, str):
            parts.append(t)
    if isinstance(narr.get("_so_what"), str):
        parts.append(narr["_so_what"])
    for item in narr.get("_action_plan", []):
        if isinstance(item, list):
            parts.append(" ".join(str(x) for x in item))
        elif isinstance(item, str):
            parts.append(item)
    for sec in order:
        v = narr.get(sec)
        if isinstance(v, str):
            parts.append(v)
    return "\n".join(parts)


def strip_citations(text: str) -> str:
    text = re.sub(r"<a\b[^>]*>.*?</a>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)            # other tags (<code>, <p>, <b>)
    text = text.replace("&quot;", '"').replace("&laquo;", "«").replace("&raquo;", "»")
    text = re.sub(r"\(\s*\)", "", text)            # empty parens left by stripped citations
    return text


def check(topic: str) -> list:
    text = strip_citations(reading_order_text(topic))
    problems = []
    for label, pat in TERMS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue  # term not present — nothing to explain
        s, e = m.start(), m.end()
        after = text[e: e + GAP_AFTER]
        before = text[max(0, s - 90): s]
        if GLOSS_AFTER.search(after) or GLOSS_BEFORE.search(before):
            continue
        snippet = text[max(0, s - 10): e + 70].replace("\n", " ")
        problems.append((label, snippet))
    return problems


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "topic1"
    problems = check(topic)
    if not problems:
        print("✓ term gate: every jargon term is explained at first mention")
        return 0
    print(f"✗ term gate: {len(problems)} term(s) without an explanation at first mention:")
    for label, snippet in problems:
        print(f"  • {label}: …{snippet}…")
    print("  Explain each at FIRST mention: «term (what it means in 3-7 plain words)».")
    return 1


if __name__ == "__main__":
    sys.exit(main())
