#!/usr/bin/env python3
"""Single orchestrator for the deterministic tail of the funnel (with gates between stages).

Stage order is defined HERE and nowhere else. Before each stage — input check,
after — output check; the first failed stage stops everything with a clear message.
Before printing stands the hard guard (gate). Therefore the order cannot be broken, and
an unconfirmed fact will not reach the report.

This script runs what does NOT require a model. Agentic stages (engines, fact-checking,
section clarification, re-sourcing) are handled by the /research skill BEFORE this runs —
so the first gate checks that verdicts already exist.

Usage: python3 funnel/run.py <topic> ["Report Title"] [--publish] [--domain <domain>] [--paged]
"""
import sys
import json
import subprocess
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import contracts as C
import paths as P
from contracts import StageError

ROOT = C.ROOT
PY = sys.executable
_args = [a for a in sys.argv[1:] if not a.startswith("-")]
_flags = [a for a in sys.argv[1:] if a.startswith("-")]
topic = _args[0] if _args else None
title = _args[1] if len(_args) > 1 else None
PUBLISH = "--publish" in _flags

# --domain <value> support: pull value after the flag
_domain = None
for _i, _f in enumerate(_flags):
    if _f == "--domain" and _i + 1 < len(_flags):
        _domain = _flags[_i + 1]
        break
# also check raw argv (--domain value may not start with -)
_raw = sys.argv[1:]
if "--domain" in _raw:
    _di = _raw.index("--domain")
    if _di + 1 < len(_raw):
        _domain = _raw[_di + 1]

if not topic:
    print("topic required: python3 funnel/run.py <topic> [\"Title\"] [--publish] [--domain <domain>] [--paged]")
    sys.exit(2)
if not title:
    title = f"Verified Report — {topic}"


def _cfg():
    # Config is scaffolded mid-chain (scaffold_config stage), so it may not exist
    # yet when renderer selection is first evaluated. Treat a missing config as
    # empty defaults rather than crashing the chain before bootstrap.
    p = P.config(topic)
    if not p.exists():
        return {}
    return json.loads(p.read_text("utf-8"))


# Renderer selection: paged (consulting paginated layout) — default for all reports;
# compact final stays only with explicit opt-out: "renderer": "final" in config OR --final flag.
def use_paged():
    if "--final" in _flags or _cfg().get("renderer") == "final":
        return False
    return True


def report_html():
    """Path to the assembled HTML. The paged renderer writes alongside as ...-paged.html (see render_paged.py)."""
    out = _cfg().get("out", f"reports/REPORT-{topic}.html")
    if use_paged():
        out = out.replace(".html", "-paged.html")
    return str(ROOT / out)

# Stage order — single source of truth. (name, command|thunk, before, after, condition, soft)
# Re-sourcing (resourced) is merged INSIDE build_pool — the pool is entirely derived from verdicts+re-sourcing.
# Soft stage: its failure does not kill the chain (no Chrome for PDF / no vault for publish).
STAGES = [
    ("build_pool",
     [PY, "funnel/build_pool.py", topic],
     lambda: C.validate_verdicts(topic),
     lambda: (C.validate_raw(topic), C.validate_pool(topic)),
     True, False),
    ("coverage_audit (count audit)",
     [PY, "funnel/coverage_audit.py", topic],
     None,
     None,
     True, True),                     # soft: under-coverage flag warns, does not block
    ("RELEVANCE (fact on-topic)",
     [PY, "funnel/relevance_gate.py", topic],
     None,
     None,
     True, True),                     # soft: relevance is a judgement; warns, does not block
    ("audit_rejected",
     [PY, "funnel/audit_rejected.py", topic],
     lambda: C.validate_raw(topic),
     lambda: C.validate_audit(topic),
     True, False),
    ("enrich_sources",
     [PY, "funnel/enrich_sources.py", topic],
     lambda: C.validate_pool(topic),
     lambda: C.validate_pool(topic, require_source_name=True),
     True, False),
    ("scaffold_config",
     [PY, "funnel/scaffold_config.py", topic, title],
     None,
     lambda: C.validate_config(topic),
     True, False),
    ("GATE (hard guard)",
     [PY, "funnel/gate.py", topic],
     None,
     None,
     True, False),
    ("PROSE (numbers in narratives)",
     [PY, "funnel/prose_gate.py", topic],
     None,
     None,
     True, True),                     # soft: warns, does not block
    ("SYNC (prose freshness + section completeness)",
     [PY, "funnel/sync_gate.py", topic]
     + (["--accept-stale"] if "--accept-stale" in _flags else []),
     None,
     None,
     True, False),                    # HARD: stale prose / fact without a section → block
    ("TERMS (jargon explained)",
     [PY, "funnel/term_gate.py", topic],
     None,
     None,
     True, False),                    # HARD: term without an explanation at first mention → block
    ("CITATIONS (hrefs point into the pool)",
     [PY, "funnel/citation_gate.py", topic],
     None,
     None,
     True, False),                    # HARD: truncated/foreign URL in prose → block
    ("SCOPE (no personal context)",
     [PY, "funnel/scope_gate.py", topic, "--hard"],
     None,
     None,
     True, False),                    # HARD: visa/media pack/health in the report → block
    ("render (paged)" if use_paged() else "render_final",
     [PY, "render_paged.py", topic] if use_paged() else [PY, "render_final.py", topic],
     lambda: C.validate_config(topic),
     lambda: C.validate_report(topic, paged=use_paged()),
     True, False),
    ("render_pdf",
     lambda: ["bash", "render_pdf.sh", report_html()],
     None,
     None,
     True, True),                      # soft: no Chrome → warning, not a block
    ("publish (wiki)",
     [PY, "funnel/publish.py", topic]
     + (["--paged"] if use_paged() else [])
     + (["--domain", _domain] if _domain else []),
     None,
     None,
     PUBLISH, True),                   # only with --publish; soft: no vault → skip
    ("telemetry (log)",
     [PY, "funnel/telemetry.py", topic],
     None,
     None,
     True, True),                      # soft: log failure must not kill the report
    ("evidence (page archive)",
     [PY, "funnel/archive_evidence.py", topic],
     None,
     None,
     True, True),                      # soft: no cache → warning, not a block
    ("catalog (topic catalog)",
     [PY, "funnel/catalog.py"],
     None,
     None,
     True, True),                      # soft: catalog failure must not kill the report
]


def run():
    for name, cmd, pre, post, cond, soft in STAGES:
        if not cond:
            continue
        if pre:
            try:
                pre()
            except StageError as e:
                print(f"✗ {name}: input not ready — {e}")
                sys.exit(1)
        r = subprocess.run(cmd() if callable(cmd) else cmd, cwd=ROOT)
        if r.returncode != 0:
            if soft:
                print(f"⚠ {name}: skipped (code {r.returncode}) — not critical, continuing")
                continue
            print(f"✗ {name}: failed (code {r.returncode}). Chain stopped.")
            sys.exit(1)
        if post:
            try:
                post()
            except StageError as e:
                print(f"✗ {name}: output has wrong shape — {e}")
                sys.exit(1)
        print(f"✓ {name}")
    size = C.validate_report(topic, paged=use_paged())
    rel = pathlib.Path(report_html()).relative_to(ROOT)
    # Append-only run receipt: git sha + content hashes of pool/config -> report (drift trail).
    try:
        import receipts
        receipts.stamp(topic, "run",
                       inputs=[P.pool(topic), P.config(topic)],
                       outputs=[pathlib.Path(report_html())])
    except Exception as e:
        print(f"⚠ receipt skipped: {e}")
    print(f"\n✓ done: {rel} ({size // 1024} KB)")


if __name__ == "__main__":
    run()
