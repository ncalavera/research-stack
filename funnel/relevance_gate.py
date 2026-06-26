#!/usr/bin/env python3
"""relevance_gate — the third axis of control: "the fact is on-topic for the report".

The hard guard catches lies (text↔live source), term/citation/prose catch form. But a
true, well-formed, yet OFF-TOPIC fact passes every gate legitimately. Relevance is a
semantic judgement and cannot be caught with a regex, so the gate leans on LLM verdicts
and itself does only the deterministic part.

The relevance rubric already lives in the topic: `persona` + `questions` from facts.json
and `question.txt`. A judge (Opus, run after build_pool) reads them and decides on/off-scope
per pool fact, writing `topics/<topic>/relevance_review.json`:
  {"reviewed_fids_hash": "<sha1 of pool fid set>", "verdicts": {"<fid>": {"scope":"on|off","reason":"..."}}}

Modes:
  python3 funnel/relevance_gate.py <topic>            # audit: what is unreviewed / what off-scope is still in the pool
  python3 funnel/relevance_gate.py <topic> --rubric   # print the rubric (persona+questions) for the judge
  python3 funnel/relevance_gate.py <topic> --apply    # off-scope verdicts → exclude.json (with a log)

Soft by nature (relevance is a judgement, not a fact): with no review, or a stale one, it
WARNS (exit 0), it does not block. Hard mode --hard gives exit 1 when the review is missing
or off-scope facts are still in the pool (for published reports in run.py — your choice).
"""
import hashlib
import json
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P


def _file(topic, name):
    return P.topic_dir(topic) / name


def _load(topic, name, default=None):
    p = _file(topic, name)
    if not p.exists():
        return default
    return json.loads(p.read_text("utf-8"))


def pool_fids(topic):
    pool = _load(topic, "pool.json", {"facts": []})
    facts = pool if isinstance(pool, list) else pool.get("facts", [])
    return [f["fid"] for f in facts], facts


def fids_hash(fids):
    return hashlib.sha1("\n".join(sorted(fids)).encode()).hexdigest()[:16]


def rubric(topic):
    facts = _load(topic, "facts.json", {}) or {}
    persona = facts.get("persona", "")
    qs = "\n".join(f"- {q.get('id')}: {q.get('q')}" for q in facts.get("questions", []))
    qtext = ""
    qp = P.question(topic)
    if qp.exists():
        qtext = qp.read_text("utf-8").strip()
    return persona, qs, qtext


def audit(topic, hard=False):
    fids, facts = pool_fids(topic)
    review = _load(topic, "relevance_review.json")
    problems = []
    if not review:
        msg = f"relevance not reviewed ({len(fids)} facts) — the judge (Opus) was not run"
        problems.append(msg)
        return problems, "missing"
    cur = fids_hash(fids)
    if review.get("reviewed_fids_hash") != cur:
        problems.append("relevance_review.json is stale: the pool changed after review — re-run the judge")
    verdicts = review.get("verdicts", {})
    # off-scope, but still in the pool (not filtered out via exclude.json)
    off_in_pool = [fid for fid in fids if verdicts.get(fid, {}).get("scope") == "off"]
    for fid in off_in_pool:
        f = next((x for x in facts if x["fid"] == fid), {})
        txt = (f.get("corrected") or f.get("text", ""))[:80]
        problems.append(f"off-scope in pool [{fid}]: {txt} — reason: {verdicts[fid].get('reason','')}")
    return problems, ("dirty" if off_in_pool else "clean")


def apply_offscope(topic):
    review = _load(topic, "relevance_review.json") or {}
    verdicts = review.get("verdicts", {})
    fids, facts = pool_fids(topic)
    # fid → anchor_id (exclude.json keys by engine:cid)
    fid2anchor = {f["fid"]: f.get("anchor_id") for f in facts}
    excl = _load(topic, "exclude.json", {"exclude": []})
    excl.setdefault("exclude", [])
    added = []
    for fid, v in verdicts.items():
        if v.get("scope") != "off":
            continue
        a = fid2anchor.get(fid)
        if a and a not in excl["exclude"]:
            excl["exclude"].append(a)
            added.append((a, v.get("reason", "")))
    excl.setdefault("_relevance_log", []).extend(
        {"anchor": a, "reason": r} for a, r in added)
    _file(topic, "exclude.json").write_text(
        json.dumps(excl, ensure_ascii=False, indent=2), "utf-8")
    for a, r in added:
        print(f"  off-scope → exclude: {a} ({r[:60]})")
    print(f"relevance applied: {len(added)} added to exclude. Rebuild build_pool.")
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    topic = args[0] if args else "topic1"
    if "--rubric" in flags:
        persona, qs, qtext = rubric(topic)
        print("PERSONA:\n" + persona + "\n\nQUESTIONS:\n" + qs + "\n\nQUESTION.TXT:\n" + qtext)
        return 0
    if "--apply" in flags:
        return apply_offscope(topic)
    hard = "--hard" in flags
    problems, state = audit(topic, hard)
    if state == "clean" and not problems:
        print("✓ relevance gate: every fact is reviewed and on-topic")
        return 0
    mark = "✗" if (hard and problems) else "⚠"
    print(f"{mark} relevance gate ({state}):")
    for p in problems:
        print(f"  • {p}")
    if state == "missing":
        print("  Run the judge: relevance_gate.py <topic> --rubric → Opus judges pool.json → relevance_review.json")
    elif state == "dirty":
        print("  Filter: relevance_gate.py <topic> --apply  (off-scope → exclude.json), then build_pool.")
    return 1 if (hard and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
