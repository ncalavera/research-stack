#!/usr/bin/env python3
"""Single source of funnel paths — topics/<topic>/ layout.

All functions take topic (and engine where needed) and return pathlib.Path.
No legacy fallback: only the new contract.

Central layout:
    topics/<topic>/
      question.txt
      facts.json
      engines/<engine>.json      raw engine output (report + sources)
      atoms/<engine>.json        atoms after atomize.js
      verdicts/<engine>[__rN].json  fact-check verdicts
      selection.json
      pool.json
      pool_raw.json
      pool_resourced.json
      sections.json
      contradictions.json
      audit_rejected.json
      narratives.json
      config.json
      evidence/
      manifest.json
"""
import os
from pathlib import Path

# Repo root holds the bundled `topics/example` only. Real research data lives in
# an external vault selected by RESEARCH_VAULT so the public repo stays clean.
REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT = REPO_ROOT  # back-compat alias for callers that referenced paths.ROOT


# ── data root resolution (RESEARCH_VAULT) ────────────────────────────────────

def _vault_root() -> "Path | None":
    """Return the configured vault root, or None when RESEARCH_VAULT is unset.

    A RESEARCH_VAULT pointing at a missing directory is an error rather than a
    silent fall-through to a repo write.
    """
    v = os.environ.get("RESEARCH_VAULT")
    if not v:
        return None
    p = Path(v).expanduser()
    if not p.exists():
        raise FileNotFoundError(
            f"RESEARCH_VAULT points to a non-existent directory: {p}"
        )
    return p


def topics_root_for(topic: str) -> Path:
    """Resolve the topics/ root holding this topic.

    Precedence:
      1. RESEARCH_VAULT unset       -> repo `topics/` (bundled example / demo / CI).
      2. vault set, topic in vault  -> `$RESEARCH_VAULT/topics`.
      3. vault set, otherwise       -> `$RESEARCH_VAULT/topics` (new topic).

    When a vault is configured it always owns reads and writes, so a run can
    never write into the git-tracked `topics/example` fixture. The bundled
    example is a no-vault demo: run it with RESEARCH_VAULT unset.
    """
    vault = _vault_root()
    if vault is None:
        return REPO_ROOT / "topics"
    return vault / "topics"


# ── topic directory ──────────────────────────────────────────────────────────

def topic_dir(topic: str) -> Path:
    return topics_root_for(topic) / topic


# ── topic input data ─────────────────────────────────────────────────────────

def question(topic: str) -> Path:
    return topic_dir(topic) / "question.txt"


def facts(topic: str) -> Path:
    return topic_dir(topic) / "facts.json"


# ── raw engine output ────────────────────────────────────────────────────────

def engines_dir(topic: str) -> Path:
    return topic_dir(topic) / "engines"


def engine_raw(topic: str, engine: str) -> Path:
    return engines_dir(topic) / f"{engine}.json"


# ── atoms ────────────────────────────────────────────────────────────────────

def atoms_dir(topic: str) -> Path:
    return topic_dir(topic) / "atoms"


def atoms(topic: str, engine: str) -> Path:
    return atoms_dir(topic) / f"{engine}.json"


# ── selection ────────────────────────────────────────────────────────────────

def selection(topic: str) -> Path:
    return topic_dir(topic) / "selection.json"


def select_by_source(topic: str) -> Path:
    return topic_dir(topic) / "select_by_source.json"


# ── verdicts ─────────────────────────────────────────────────────────────────

def verdicts_dir(topic: str) -> Path:
    return topic_dir(topic) / "verdicts"


# ── fact pool ────────────────────────────────────────────────────────────────

def pool(topic: str) -> Path:
    return topic_dir(topic) / "pool.json"


def pool_raw(topic: str) -> Path:
    return topic_dir(topic) / "pool_raw.json"


def pool_resourced(topic: str) -> Path:
    return topic_dir(topic) / "pool_resourced.json"


def sections(topic: str) -> Path:
    return topic_dir(topic) / "sections.json"


def contradictions(topic: str) -> Path:
    return topic_dir(topic) / "contradictions.json"


# ── audit ────────────────────────────────────────────────────────────────────

def audit(topic: str) -> Path:
    return topic_dir(topic) / "audit_rejected.json"


# ── layout (narratives + config) ─────────────────────────────────────────────

def narratives(topic: str) -> Path:
    return topic_dir(topic) / "narratives.json"


def narratives_lock(topic: str) -> Path:
    return topic_dir(topic) / "narratives.lock"


def config(topic: str) -> Path:
    return topic_dir(topic) / "config.json"


def clarity_lock(topic: str) -> Path:
    return topic_dir(topic) / "clarity.lock"


# ── run artifacts ────────────────────────────────────────────────────────────

def evidence_dir(topic: str) -> Path:
    return topic_dir(topic) / "evidence"


def manifest(topic: str) -> Path:
    return topic_dir(topic) / "manifest.json"
