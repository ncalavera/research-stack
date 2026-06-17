#!/usr/bin/env python3
"""Normalises the output of deep-research-cheap.js (task output file) into
topics/<topic>/engines/claude_deepresearch.json in the engine participant format.
Usage: save_claude_dr.py <output_file> <topic_num> <seconds>"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "funnel"))
import paths as P

outfile, topic = sys.argv[1], sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else None
d = json.load(open(outfile))
agents = d.get("agentCount")
r = d.get("result", d)

parts = [r.get("summary", "").strip(), ""]
for f in r.get("findings", []):
    parts.append(f.get("claim", "").strip())
    if f.get("evidence"):
        parts.append("  Evidence base: " + f["evidence"].strip())
    parts.append(f"  [confidence: {f.get('confidence','')}, vote: {f.get('vote','')}]")
    parts.append("")
caveats = r.get("caveats", [])
if isinstance(caveats, str):  # sometimes the workflow returns caveats as a string — don't iterate char-by-char
    caveats = [caveats]
for c in caveats:
    parts.append("Caveat: " + (c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)))
report = "\n".join(parts).strip()

srcs = []
for f in r.get("findings", []):
    srcs += f.get("sources", [])
for s in r.get("sources", []):
    u = s.get("url") if isinstance(s, dict) else s
    if u:
        srcs.append(u)
seen = set()
srcs = [x for x in srcs if not (x in seen or seen.add(x))]

norm = {"report": report, "sources": srcs, "cost_est": None, "seconds": secs,
        "engine": "claude_deepresearch", "agentCount": agents,
        "stats": r.get("stats"), "refuted": r.get("refuted"),
        "openQuestions": r.get("openQuestions")}
# topic may be a number (legacy: topic1) or a slug (report-craft, work-pricing)
topic_dir = f"topic{topic}" if str(topic).isdigit() else str(topic)
out_path = P.engine_raw(topic_dir, "claude_deepresearch")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(norm, ensure_ascii=False, indent=2))
print(f"saved {out_path}: report {len(report)} chars, {len(srcs)} sources, {agents} subagents")
