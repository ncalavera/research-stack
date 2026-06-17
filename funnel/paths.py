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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── topic directory ──────────────────────────────────────────────────────────

def topic_dir(topic: str) -> Path:
    return ROOT / "topics" / topic


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


def config(topic: str) -> Path:
    return topic_dir(topic) / "config.json"


# ── run artifacts ────────────────────────────────────────────────────────────

def evidence_dir(topic: str) -> Path:
    return topic_dir(topic) / "evidence"


def manifest(topic: str) -> Path:
    return topic_dir(topic) / "manifest.json"
