#!/usr/bin/env python3
"""Pipeline health auditor.

Two modes:
  Global (no --topic): syntax check, env key presence, run test suite.
  Topic  (--topic T):  engine-status audit + contract chain for one topic.

Exit codes:
  0 — no hard failures
  1 — syntax error, test suite failed, or topic dir missing
"""
import argparse
import os
import pathlib
import py_compile
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P
from contracts import (
    StageError,
    validate_atoms,
    validate_config,
    validate_pool,
    validate_report,
    validate_selection,
    validate_verdicts,
    verdict_quote_offenders,
)
from engine_status import audit_topic, print_summary

ROOT = P.ROOT

# ── helpers ──────────────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


# ── global mode ───────────────────────────────────────────────────────────────

def check_python_syntax() -> int:
    """Compile every *.py under repo root and funnel/. Returns error count."""
    skip_dirs = {"__pycache__", "_archive", ".bakeoff"}
    errors = 0
    files = []
    for p in ROOT.rglob("*.py"):
        if any(part in skip_dirs for part in p.parts):
            continue
        files.append(p)
    files.sort()
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            _fail(f"syntax error: {f.relative_to(ROOT)} — {e}")
            errors += 1
    if not errors:
        _ok(f"Python syntax: {len(files)} files OK")
    return errors


def check_js_syntax() -> int:
    """Run node --check on known JS files at repo root. Returns error count."""
    js_files = [
        ROOT / "atomize.js",
        ROOT / "check_claims.js",
        ROOT / "deep-research-cheap.js",
        ROOT / "resource.js",
    ]
    # Check if node is available
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        _warn("node not found — JS syntax check skipped")
        return 0

    errors = 0
    checked = 0
    for f in js_files:
        if not f.exists():
            continue
        checked += 1
        result = subprocess.run(
            ["node", "--check", str(f)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            _fail(f"JS syntax error: {f.name} — {result.stderr.strip()[:120]}")
            errors += 1
    if not errors:
        _ok(f"JS syntax: {checked} files OK")
    return errors


def check_env_keys() -> None:
    """Warn about absent API keys (missing != broken; not all are always needed)."""
    keys = ["GEMINI_API_KEY", "PERPLEXITY_API_KEY", "OPENAI_API_KEY", "EXA_API_KEY"]
    missing = [k for k in keys if not os.environ.get(k)]
    present = [k for k in keys if os.environ.get(k)]
    if present:
        _ok(f"env keys present: {', '.join(present)}")
    for k in missing:
        _warn(f"env key absent: {k} (may not be needed)")


def run_tests() -> int:
    """Run test_funnel.py as a subprocess. Returns 0 on pass, 1 on fail."""
    test_path = ROOT / "funnel" / "test_funnel.py"
    result = subprocess.run(
        [sys.executable, str(test_path)],
        capture_output=True, text=True,
    )
    # Parse summary line: "N passed, M failed"
    summary = ""
    for line in result.stdout.splitlines():
        if "passed" in line and "failed" in line:
            summary = line.strip()
    if result.returncode == 0:
        _ok(f"test_funnel: {summary or 'all passed'}")
        return 0
    else:
        _fail(f"test_funnel FAILED: {summary or 'see output below'}")
        # Print last few lines for context without flooding
        lines = result.stdout.strip().splitlines()
        for line in lines[-10:]:
            print(f"    {line}")
        return 1


def run_global() -> int:
    """Global health check. Returns exit code."""
    hard_failures = 0

    print("[doctor] Python syntax")
    hard_failures += check_python_syntax()

    print("[doctor] JS syntax")
    hard_failures += check_js_syntax()

    print("[doctor] Env keys")
    check_env_keys()

    print("[doctor] Test suite")
    hard_failures += run_tests()

    if hard_failures:
        print(f"\n[doctor] FAIL — {hard_failures} hard failure(s)")
    else:
        print("\n[doctor] OK — global health check passed")
    return 1 if hard_failures else 0


# ── topic mode ────────────────────────────────────────────────────────────────

def _run_contract(label: str, fn, *args, **kwargs):
    """Call fn(*args, **kwargs); print ✓/✗ line. Returns (ok: bool, result)."""
    try:
        result = fn(*args, **kwargs)
        _ok(f"{label}: {result}")
        return True, result
    except StageError as e:
        _fail(f"{label}: {e}")
        return False, None
    except Exception as e:
        _fail(f"{label}: unexpected error — {e}")
        return False, None


def run_topic(topic: str) -> int:
    """Audit one topic. Returns exit code."""
    tdir = P.topic_dir(topic)
    if not tdir.exists():
        _fail(f"topic dir not found: {tdir}")
        return 1

    # Engine status
    print(f"[doctor] Engine status — {topic}")
    audit = audit_topic(topic)
    if audit:
        print_summary(topic, audit)
    else:
        _warn("no engine files in engines/")

    # Contract chain (pipeline order); later-stage failures are normal mid-pipeline
    print(f"[doctor] Contracts — {topic}")
    _run_contract("validate_atoms", validate_atoms, topic)
    _run_contract("validate_selection", validate_selection, topic)
    _run_contract("validate_verdicts", validate_verdicts, topic)
    _run_contract("validate_pool", validate_pool, topic)
    _run_contract("validate_config", validate_config, topic)
    _run_contract("validate_report", validate_report, topic)

    # Soft check: quote completeness
    try:
        offenders = verdict_quote_offenders(topic)
        if offenders:
            _warn(f"verdict_quote_offenders: {len(offenders)} confirmed claim(s) missing quote (presentation only)")
        else:
            _ok("verdict_quote_offenders: all confirmed claims have quotes")
    except Exception as e:
        _warn(f"verdict_quote_offenders: {e}")

    print(f"\n[doctor] topic {topic} — audit complete (contract failures may reflect pipeline stage)")
    return 0


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Research pipeline health auditor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--topic", metavar="TOPIC", help="Audit one topic only")
    args = parser.parse_args()

    if args.topic:
        sys.exit(run_topic(args.topic))
    else:
        sys.exit(run_global())


if __name__ == "__main__":
    main()
