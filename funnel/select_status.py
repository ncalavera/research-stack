#!/usr/bin/env python3
"""Coverage and reserve tracker for the funnel with selection (step 3c).

Contract for the selection/<topic>.json file
────────────────────────────────────
File written by the Opus selector (step 3b) after ranking atoms by sub-questions.
Format:

{
  "topic": "<topic>",
  "questions": {
    "<qid>": {
      "ranked": ["<engine>:<id>", ...],   // all claim_refs for this question, by descending priority
      "verified": ["<engine>:<id>", ...]  // claim_refs already sent for verification (initially = top 3-5)
    }
  },
  "claims": {
    "<engine>:<id>": {
      "engine": "<engine>",
      "id": "<claim_id>",          // e.g. "c1"
      "text": "<claim text>",
      "source": "<url or null>",
      "has_number": true/false
    }
  }
}

claim_ref = "<engine>:<id>", e.g. "perplexity_sonar:c3".

Verdict file (judge_claims/verdicts/<topic>/<engine>.json and rounds __rN):
Looks for fields claims[].id and claims[].label — standard check_claims.js output.

Coverage logic:
- covered      ≥1 confirmed (SUPPORTED/PARTIAL) claim in ranked for this question
- pending      has ranked claims without a verdict (can still send for verification)
- exhausted    all ranked claims have a verdict, none confirmed
- NEXT         highest ranked claim without a verdict (first candidate for next_batch)

Output --json:
{
  "covered":    ["<qid>", ...],
  "next_batch": {"<engine>": [<claim_object>, ...], ...},
  "exhausted":  ["<qid>", ...]
}

Exit codes:
  0 — all questions covered or exhausted (verification complete)
  3 — next_batch non-empty (another round of check_claims needed)
"""
import sys
import json
import glob
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent  # repository root (script in funnel/)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

CONFIRMED_LABELS = {"SUPPORTED", "PARTIAL"}


def load_selection(topic: str) -> dict:
    """Reads topics/<topic>/selection.json and validates top-level shape."""
    path = P.selection(topic)
    if not path.exists():
        print(f"[select_status] ERROR: selection file not found: {path}", file=sys.stderr)
        sys.exit(2)
    data = json.loads(path.read_text())
    # Basic format validation
    for key in ("topic", "questions", "claims"):
        if key not in data:
            print(f"[select_status] ERROR: selection file missing key '{key}'", file=sys.stderr)
            sys.exit(2)
    return data


def load_verdicts(topic: str) -> dict[tuple[str, str], str]:
    """Reads all verdicts for the topic (including rounds __rN).

    Returns: (engine, claim_id) → label
    Scans topics/<topic>/verdicts/*.json including *__r2.json etc.
    """
    verdicts: dict[tuple[str, str], str] = {}
    pattern = str(P.verdicts_dir(topic) / "*.json")
    for fpath in glob.glob(pattern):
        try:
            data = json.loads(pathlib.Path(fpath).read_text())
        except Exception:
            continue
        # Filename: <engine>.json or <engine>__rN.json → engine = stem without __rN
        stem = pathlib.Path(fpath).stem
        engine = stem.split("__")[0]
        for claim in data.get("claims", []):
            cid = claim.get("id")
            label = claim.get("label")
            if cid and label:
                key = (engine, cid)
                # With multiple rounds — last verdict wins (glob in alphabetical order,
                # __r2 > original → will overwrite; this is correct: last round is most current)
                verdicts[key] = label
    return verdicts


def parse_claim_ref(ref: str) -> tuple[str, str]:
    """Parses claim_ref of the form 'engine:c3' → ('engine', 'c3')."""
    parts = ref.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid claim_ref: {ref!r}")
    return parts[0], parts[1]


def compute_coverage(selection: dict, verdicts: dict) -> dict:
    """Computes status for each sub-question.

    Returns dict with keys:
      covered    list of qid with ≥1 confirmed claim
      pending    list of qid with ranked claims without a verdict
      exhausted  list of qid where all ranked claims are verified and none confirmed
      next_map   {qid: claim_ref} — next candidate for pending questions
    """
    covered = []
    pending_next: dict[str, str] = {}  # qid → claim_ref of next candidate
    exhausted = []

    for qid, qdata in selection.get("questions", {}).items():
        ranked: list[str] = qdata.get("ranked", [])
        if not ranked:
            exhausted.append(qid)
            continue

        has_confirmed = False
        next_candidate: str | None = None

        for ref in ranked:
            try:
                engine, cid = parse_claim_ref(ref)
            except ValueError:
                continue
            label = verdicts.get((engine, cid))
            if label in CONFIRMED_LABELS:
                has_confirmed = True
                break  # question covered — can stop looking
            if label is None and next_candidate is None:
                # First ranked without a verdict — next to verify
                next_candidate = ref

        if has_confirmed:
            covered.append(qid)
        elif next_candidate is not None:
            pending_next[qid] = next_candidate
        else:
            exhausted.append(qid)

    return {
        "covered": covered,
        "pending_next": pending_next,
        "exhausted": exhausted,
    }


def build_next_batch(
    pending_next: dict[str, str], claims_map: dict
) -> dict[str, list[dict]]:
    """Groups next candidates by engine for passing to check_claims.js args.claims."""
    by_engine: dict[str, list[dict]] = {}
    for ref in pending_next.values():
        claim_data = claims_map.get(ref)
        if not claim_data:
            continue
        engine = claim_data.get("engine", ref.split(":")[0])
        by_engine.setdefault(engine, []).append(claim_data)
    return by_engine


def print_human(topic: str, coverage: dict, selection: dict, verdicts: dict) -> None:
    """Prints a readable coverage status report."""
    questions = selection.get("questions", {})
    claims_map = selection.get("claims", {})
    pending_next = coverage["pending_next"]

    print(f"\n=== select_status: {topic} ===\n")
    print(f"  Total sub-questions : {len(questions)}")
    print(f"  Covered            : {len(coverage['covered'])}")
    print(f"  Pending            : {len(pending_next)}")
    print(f"  Exhausted          : {len(coverage['exhausted'])}")
    print()

    for qid, qdata in questions.items():
        ranked: list[str] = qdata.get("ranked", [])
        status_tag = (
            "COVERED" if qid in coverage["covered"]
            else "EXHAUSTED" if qid in coverage["exhausted"]
            else "PENDING"
        )
        print(f"  [{status_tag}] {qid}")

        for ref in ranked:
            try:
                engine, cid = parse_claim_ref(ref)
            except ValueError:
                continue
            label = verdicts.get((engine, cid), "—")
            claim_text = claims_map.get(ref, {}).get("text", "")
            short = claim_text[:80] + ("…" if len(claim_text) > 80 else "")
            marker = ""
            if qid in pending_next and pending_next[qid] == ref:
                marker = " ← NEXT"
            print(f"    {engine}:{cid} [{label}]{marker}  {short!r}")

        if qid in coverage["exhausted"]:
            print("    → all ranked claims verified, none confirmed")
        print()


def main() -> None:
    """Entry point: python3 funnel/select_status.py <topic> [--json]"""
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print("Usage: python3 funnel/select_status.py <topic> [--json]", file=sys.stderr)
        sys.exit(2)

    topic = args[0]
    json_mode = "--json" in args

    selection = load_selection(topic)
    verdicts = load_verdicts(topic)
    coverage = compute_coverage(selection, verdicts)

    next_batch = build_next_batch(coverage["pending_next"], selection.get("claims", {}))

    if json_mode:
        out = {
            "covered": coverage["covered"],
            "next_batch": next_batch,
            "exhausted": coverage["exhausted"],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_human(topic, coverage, selection, verdicts)

    # Exit 0 — all covered or exhausted; 3 — more to verify
    if next_batch:
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
