#!/usr/bin/env python3
"""Publish the final report to the vault. Report + PDF + index card.

Places into the vault catalog (env RESEARCH_VAULT) under library/research/<domain>/<topic>/:
  REPORT-<topic>.html   — journal report (copy)
  REPORT-<topic>.pdf    — PDF (if built)
  index.md              — card for Obsidian: header + key findings + links

index.md is needed because Obsidian does not search inside HTML/PDF and does not create wiki-links to them.
The card makes the report discoverable by search and linkable to people/companies via [[links]].

Usage: python3 funnel/publish.py <topic> ["Topic Question"] [--domain <domain>] [--paged]

Vault is set by the RESEARCH_VAULT environment variable (default ~/research-vault).

<domain> — knowledge domain (ai, business, career, creativity, data-science, design,
           engineering, psychology, science, writing). Without --domain the report goes to
           library/research/_inbox/<topic>/ — move manually to the correct domain.
"""
import sys, json, shutil, pathlib, datetime, argparse, os

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path(os.environ.get("RESEARCH_VAULT", str(pathlib.Path.home() / "research-vault")))
RESEARCH_BASE = VAULT / "library" / "research"

# ── CLI ────────────────────────────────────────────────────────────────────────
def _available_domains():
    if RESEARCH_BASE.exists():
        return sorted(p.name for p in RESEARCH_BASE.iterdir()
                      if p.is_dir() and not p.name.startswith("."))
    return []

parser = argparse.ArgumentParser(
    description="Publish a research-stack report to the Obsidian vault.",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=f"Available domains: {', '.join(_available_domains()) or '(vault not found)'}",
)
parser.add_argument("topic", nargs="?", default="topic1")
parser.add_argument("question", nargs="?", default="")
parser.add_argument("--domain", default=None,
                    help="knowledge-domain subfolder (e.g. ai, career, design). "
                         "Omit to land in _inbox — move manually afterward.")
parser.add_argument("--paged", action="store_true",
                    help="use the paged-renderer output (*-paged.html/.pdf)")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

args, _unknown = parser.parse_known_args()
topic = args.topic
question = args.question
# legacy bare --paged flag support (run.py passes it positionally-style)
paged = args.paged or "--paged" in sys.argv


def load(path, default=None):
    p = pathlib.Path(path)
    return json.loads(p.read_text("utf-8")) if p.exists() else default


cfg = load(P.config(topic), {}) or {}
pool = load(P.pool(topic), {"facts": []})
facts = pool.get("facts", [])
if not facts:
    print(f"pool for {topic} is empty — nothing to publish")
    sys.exit(1)

if not VAULT.exists():
    print(f"vault not found: {VAULT} — skipping publish")
    sys.exit(0)

_out = cfg.get("out", f"reports/REPORT-{topic}.html")
# paged renderer writes alongside as ...-paged.html/.pdf — publish those
if paged or cfg.get("renderer") == "paged":
    paged = True
    _out = _out.replace(".html", "-paged.html")
html_src = ROOT / _out
pdf_src = html_src.with_suffix(".pdf")
title = cfg.get("page_title") or cfg.get("title_html") or f"Report — {topic}"
dek = cfg.get("dek", "")
if not question:
    q = P.question(topic)
    question = q.read_text("utf-8").strip().splitlines()[0] if q.exists() else ""

# ── Destination path ───────────────────────────────────────────────────────────
domain = args.domain
if not domain:
    domain = "_inbox"
    print(
        f"⚠  --domain not set — publishing to _inbox. "
        f"Move manually to the correct domain "
        f"({', '.join(_available_domains())}).\n"
        f"   Example: python3 funnel/publish.py {topic} --domain ai"
    )

dest = RESEARCH_BASE / domain / topic
dest.mkdir(parents=True, exist_ok=True)

# report copies
for src in (html_src, pdf_src):
    if src.exists():
        shutil.copy2(src, dest / src.name)

engines = sorted({p.get("engine") for f in facts for p in f.get("provenance", []) if p.get("engine")})
today = datetime.date.today().isoformat()


def src_link(f):
    url = f.get("best_source", "")
    name = f.get("best_source_name") or url
    yr = f.get("best_source_year")
    label = f"{name} ({yr})" if yr else name
    return f"[{label}]({url})" if url else ""


# key findings — top pool facts (sorted by engine count and class)
key = facts[:12]
lines = [f"- {f.get('text','').strip()} — {src_link(f)}" for f in key]

eng_list = ", ".join(engines)
html_name = html_src.name if html_src.exists() else ""
pdf_name = pdf_src.name if pdf_src.exists() else ""
links = " · ".join(filter(None, [
    f"[Open Report]({html_name})" if html_name else "",
    f"[PDF]({pdf_name})" if pdf_name else "",
]))

index = f"""---
title: {title}
date: {today}
type: research-report
topic: {topic}
question: {json.dumps(question, ensure_ascii=False)}
facts: {len(facts)}
engines: [{eng_list}]
source: research-stack (fact-check funnel)
---

# {title}

> {dek or question}

**Verified facts:** {len(facts)} · **Engines:** {len(engines)} ({eng_list}){(' · ' + links) if links else ''}

Every fact below is confirmed by a live source (the funnel guard does not pass unverified claims).

## Key Findings

{chr(10).join(lines)}

## Full Report

The journal version with all {len(facts)} facts, tables, and evidence base — in the files alongside: `{html_name}`{(', `' + pdf_name + '`') if pdf_name else ''}.
"""

(dest / "index.md").write_text(index, "utf-8")
print(f"→ {dest.relative_to(VAULT.parent)}/ (index.md + {html_name}{', ' + pdf_name if pdf_name else ''})")
