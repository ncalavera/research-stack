#!/usr/bin/env python3
"""State-machine driver: the single source of truth for "what stage is next" on a topic.

Why: the agentic front half of the pipeline (engines -> atomize -> selection -> check_claims)
used to live only as prose in the /research skill, so an agent could skip a stage, reorder, or
declare "done" early. This driver removes that discretion: it inspects which artifacts exist and
are valid (via the same contracts the deterministic tail uses), then prints THE one next command.
The agent runs `step.py <topic>`, does exactly what it prints, and runs it again — no guessing.

Read-only and idempotent: it never writes, only inspects. Safe to run any number of times.

Run:   python3 funnel/step.py <topic> ["Report title"]
Exit:  0 — printed the next step (or "all done");
       2 — topic does not exist.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P
import contracts as C
import engine_status as ES


def _facts_qids(topic):
    """Sub-question ids declared in facts.json (stage-1 output). [] if absent/malformed."""
    fp = P.facts(topic)
    if not fp.exists():
        return []
    try:
        import json
        d = json.loads(fp.read_text("utf-8"))
        return [q.get("id") for q in d.get("questions", []) if q.get("id")]
    except Exception:
        return []


def _usable_engines(topic):
    """Engines whose raw output is usable (ok/legacy). [] on a fresh topic."""
    audit = ES.audit_topic(topic)
    return [name for name, st in audit.items() if st["usable"]]


def _stage_input(topic):
    q = P.question(topic)
    q_ok = q.exists() and len((q.read_text("utf-8")).strip()) >= 20
    qids = _facts_qids(topic)
    done = q_ok and bool(qids)
    detail = f"question {'ok' if q_ok else 'MISSING'}, sub-questions: {len(qids)}"
    nxt = ("Stage 1 (skill): write topics/%s/question.txt (whole question for the engines) and "
           "topics/%s/facts.json (sub-questions with ids)." % (topic, topic))
    return done, detail, nxt


def _stage_engines(topic):
    usable = _usable_engines(topic)
    done = len(usable) >= 1
    detail = f"usable engines: {len(usable)} ({', '.join(usable) or '—'})"
    nxt = ("Stage 2 (engines): preflight, then launch.\n"
           "    python3 funnel/preflight_engines.py %s <engines>\n"
           "    python3 engines.py %s topics/%s/question.txt <engines> --skip-ok\n"
           "  Light: perplexity_sonar,exa_answer  ·  Deep: add perplexity_deep,openai_deep,exa_research\n"
           "  (Claude deep-research is run separately via the deep-research-cheap.js Workflow.)"
           % (topic, topic, topic))
    return done, detail, nxt


def _stage_atoms(topic):
    usable = _usable_engines(topic)
    adir = P.atoms_dir(topic)
    have = {p.stem for p in adir.glob("*.json")} if adir.exists() else set()
    missing = [e for e in usable if e not in have]
    try:
        C.validate_atoms(topic)
        valid = True
    except C.StageError as e:
        valid = False
        missing = missing or ["(invalid atoms: %s)" % e]
    done = valid and not missing
    detail = f"atoms for {len(have)} engines; missing for: {', '.join(missing) or '—'}"
    nxt = ("Stage 3a (atomize): run the atomize.js Workflow per engine still missing atoms: "
           "%s. Each: Workflow scriptPath=$RS/atomize.js args={topic:'%s', engine:'<engine>'}."
           % (', '.join(missing) or '—', topic))
    return done, detail, nxt


def _stage_selection(topic):
    try:
        r = C.validate_selection(topic)
        return True, f"selection covers {r['questions']} sub-questions", ""
    except C.StageError as e:
        nxt = ("Stage 3b (skill/Opus): write topics/%s/selection.json — for every facts.json qid a "
               "ranked[] (and verified[]) of 'engine:cN'. Reason it didn't pass: %s" % (topic, e))
        return False, f"not valid ({e})", nxt


def _stage_verdicts(topic):
    try:
        n = C.validate_verdicts(topic)
        return True, f"{n} engine verdict files", ""
    except C.StageError as e:
        nxt = ("Stage 3c (verify): free preflight, then the check_claims.js Workflow per engine.\n"
               "    python3 funnel/preflight.py %s\n"
               "  Then for each engine in select_by_source.json: Workflow scriptPath=$RS/check_claims.js "
               "args={topic:'%s', engine:'<engine>', claims:[...]}.\n  Reason: %s" % (topic, topic, e))
        return False, f"no valid verdicts ({e})", nxt


def _stage_report(topic, title):
    # The deterministic tail (build_pool -> ... -> gate -> render) is a single run.py invocation.
    for paged in (True, False):
        try:
            size = C.validate_report(topic, paged=paged)
            return True, f"report present ({size // 1024} KB, {'paged' if paged else 'final'})", ""
        except C.StageError:
            continue
    nxt = ('Stage 4-10 (deterministic tail): python3 funnel/run.py %s "%s" [--publish]\n'
           "  Runs build_pool -> audit -> enrich -> config -> GATE -> render with gates between stages."
           % (topic, title))
    return False, "no report yet", nxt


STAGES = [
    ("input",     _stage_input),
    ("engines",   _stage_engines),
    ("atoms",     _stage_atoms),
    ("selection", _stage_selection),
    ("verdicts",  _stage_verdicts),
]


def main():
    if len(sys.argv) < 2:
        print("usage: python3 funnel/step.py <topic> [\"Report title\"]", file=sys.stderr)
        sys.exit(64)
    topic = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else f"Verified report — {topic}"
    if not P.topic_dir(topic).exists():
        print(f"✗ topic does not exist: topics/{topic}/ — create question.txt + facts.json first.")
        sys.exit(2)

    print(f"=== pipeline state: {topic} ===")
    # Walk fixed-order stages; the first unmet one is the next action.
    for name, check in STAGES:
        done, detail, nxt = check(topic)
        mark = "✓" if done else "→"
        print(f"  {mark} {name}: {detail}")
        if not done:
            print(f"\nNEXT STEP:\n  {nxt}")
            sys.exit(0)

    # Front half complete. Soft warning: confirmed verdicts missing a verbatim quote.
    offenders = C.verdict_quote_offenders(topic)
    if offenders:
        print(f"  ⚠ quote: {len(offenders)} confirmed verdicts without a verbatim quote "
              f"(presentation only, not a blocker).")

    done, detail, nxt = _stage_report(topic, title)
    mark = "✓" if done else "→"
    print(f"  {mark} report: {detail}")
    if not done:
        print(f"\nNEXT STEP:\n  {nxt}")
        sys.exit(0)

    print(f"\n✓ all stages passed. Final check:\n  python3 funnel/doctor.py --topic {topic}")
    sys.exit(0)


if __name__ == "__main__":
    main()
