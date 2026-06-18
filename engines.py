#!/usr/bin/env python3
"""Run research engines on a single question. Saves report, sources, cost, time.
Each engine is isolated in try/except — one failure does not abort the run.
Prices are approximate (PRICES), marked '≈'."""
import os, sys, json, time, urllib.request, urllib.error, concurrent.futures, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "funnel"))
import paths as P

MIN_REPORT_CHARS = 200  # shorter = truncated/empty engine report (not a source of atoms)

PRICES = {  # $ per 1M tokens (approximate, mid-2026)
    "gemini-2.5-pro":      {"in": 1.25, "out": 10.0},
    "o4-mini-deep-research": {"in": 2.0, "out": 8.0},
    "sonar-pro":           {"in": 3.0, "out": 15.0, "search_per_k": 5.0},
    "sonar-deep-research": {"in": 2.0, "out": 8.0, "search_per_k": 5.0},
}

# Which env key each engine needs (source of truth for preflight_engines.py).
# claude_deepresearch runs through a Workflow and needs no env key.
ENGINE_ENV = {
    "gemini":           "GEMINI_API_KEY",
    "perplexity_sonar": "PERPLEXITY_API_KEY",
    "perplexity_deep":  "PERPLEXITY_API_KEY",
    "openai_deep":      "OPENAI_API_KEY",
    "exa_answer":       "EXA_API_KEY",
    "exa_research":     "EXA_API_KEY",
}

def _post(url, body, headers, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def _get(url, headers, timeout=120):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

# ---------- engines ----------
def run_gemini(q):
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={key}"
    t = time.time()
    r = _post(url, {"contents":[{"parts":[{"text":q}]}], "tools":[{"google_search":{}}]}, {"Content-Type":"application/json"})
    sec = time.time()-t
    c = r["candidates"][0]
    text = "".join(p.get("text","") for p in c["content"]["parts"])
    srcs = [x.get("web",{}).get("uri","") for x in c.get("groundingMetadata",{}).get("groundingChunks",[])]
    u = r.get("usageMetadata",{})
    cost = u.get("promptTokenCount",0)/1e6*PRICES["gemini-2.5-pro"]["in"] + u.get("candidatesTokenCount",0)/1e6*PRICES["gemini-2.5-pro"]["out"]
    return {"report":text, "sources":[s for s in srcs if s], "cost_est":round(cost,4), "seconds":round(sec,1),
            "usage":{"in":u.get("promptTokenCount"),"out":u.get("candidatesTokenCount")}}

def run_pplx(q, model):
    key = os.environ["PERPLEXITY_API_KEY"]
    t = time.time()
    body = {"model":model, "messages":[{"role":"user","content":q}], "web_search_options":{"search_context_size":"high"}}
    r = _post("https://api.perplexity.ai/chat/completions", body, {"Authorization":"Bearer "+key,"Content-Type":"application/json"}, timeout=600)
    sec = time.time()-t
    text = r["choices"][0]["message"]["content"]
    srcs = r.get("citations",[]) or r.get("search_results",[])
    srcs = [s if isinstance(s,str) else s.get("url","") for s in srcs]
    u = r.get("usage",{})
    p = PRICES[model]
    cost = u.get("prompt_tokens",0)/1e6*p["in"] + u.get("completion_tokens",0)/1e6*p["out"] + p.get("search_per_k",0)/1000*u.get("num_search_queries",1)
    return {"report":text, "sources":[s for s in srcs if s], "cost_est":round(cost,4), "seconds":round(sec,1),
            "usage":{"in":u.get("prompt_tokens"),"out":u.get("completion_tokens")}}

def run_openai_dr(q):
    key = os.environ["OPENAI_API_KEY"]
    h = {"Authorization":"Bearer "+key,"Content-Type":"application/json"}
    t = time.time()
    launch = _post("https://api.openai.com/v1/responses",
        {"model":"o4-mini-deep-research-2025-06-26","input":q,"tools":[{"type":"web_search_preview"}],"background":True}, h)
    if not isinstance(launch, dict) or not launch.get("id"):
        return {"error":"launch without id: "+str(launch)[:200],"seconds":round(time.time()-t,1)}
    rid = launch["id"]
    r = {}
    while True:
        time.sleep(8)
        r = _get(f"https://api.openai.com/v1/responses/{rid}", h) or {}
        if r.get("status") in ("completed","failed","incomplete","cancelled"): break
        if time.time()-t > 600: return {"error":"timeout 10min","seconds":round(time.time()-t,1)}
    sec = time.time()-t
    # A non-completed status must NOT leak as "success" with an empty report.
    if r.get("status") != "completed":
        return {"error":"status "+str(r.get("status")),"seconds":round(sec,1)}
    text, srcs = "", set()
    for it in r.get("output",[]):
        if it.get("type")=="message":
            for cc in it.get("content",[]):
                if cc.get("type")=="output_text":
                    text += cc.get("text","")
                    for a in cc.get("annotations",[]):
                        if a.get("url"): srcs.add(a["url"])
    u = r.get("usage",{})
    cost = u.get("input_tokens",0)/1e6*PRICES["o4-mini-deep-research"]["in"] + u.get("output_tokens",0)/1e6*PRICES["o4-mini-deep-research"]["out"]
    return {"report":text, "sources":list(srcs), "cost_est":round(cost,4), "seconds":round(sec,1),
            "usage":{"in":u.get("input_tokens"),"out":u.get("output_tokens")}, "status":r.get("status")}

def run_exa(q):
    key = os.environ.get("EXA_API_KEY_OVERRIDE") or os.environ["EXA_API_KEY"]
    t = time.time()
    r = _post("https://api.exa.ai/answer", {"query":q,"text":False}, {"x-api-key":key,"Content-Type":"application/json"}, timeout=300)
    sec = time.time()-t
    if r.get("error"): return {"error":r.get("error"),"seconds":round(sec,1)}
    srcs = [c.get("url","") for c in r.get("citations",[])]
    cost = r.get("costDollars",{}).get("total") if isinstance(r.get("costDollars"),dict) else None
    return {"report":r.get("answer",""), "sources":[s for s in srcs if s],
            "cost_est":cost if cost is not None else 0.005, "seconds":round(sec,1)}

def _exa_cites(cits):
    out = []
    for c in cits or []:
        if isinstance(c, str): out.append(c)
        elif isinstance(c, dict): out.append(c.get("url",""))
    return [s for s in out if s]

def run_exa_research(q, model="exa-research"):
    key = os.environ.get("EXA_API_KEY_OVERRIDE") or os.environ["EXA_API_KEY"]
    h = {"x-api-key":key,"Content-Type":"application/json"}
    t = time.time()
    launch = _post("https://api.exa.ai/research/v1", {"model":model,"instructions":q}, h, timeout=60)
    if not isinstance(launch, dict) or not launch.get("researchId"):
        return {"error":"launch without researchId: "+str(launch)[:200],"seconds":round(time.time()-t,1)}
    rid = launch["researchId"]
    r = {}
    while True:
        time.sleep(8)
        r = _get(f"https://api.exa.ai/research/v1/{rid}", h) or {}
        if r.get("status") in ("completed","failed","canceled"): break
        if time.time()-t > 600: return {"error":"timeout 10min","seconds":round(time.time()-t,1)}
    sec = time.time()-t
    if r.get("status")!="completed": return {"error":"status "+str(r.get('status')),"seconds":round(sec,1)}
    out = r.get("output",{})
    text = out.get("content","") if isinstance(out,dict) else str(out)
    cost = r.get("costDollars",{}).get("total") if isinstance(r.get("costDollars"),dict) else None
    return {"report":text, "sources":_exa_cites(r.get("citations",[])),
            "cost_est":cost, "seconds":round(sec,1)}

ENGINES = {
    "gemini":        lambda q: run_gemini(q),
    "perplexity_sonar": lambda q: run_pplx(q,"sonar-pro"),
    "perplexity_deep":  lambda q: run_pplx(q,"sonar-deep-research"),
    "openai_deep":   lambda q: run_openai_dr(q),
    "exa_answer":    lambda q: run_exa(q),
    "exa_research":  lambda q: run_exa_research(q),
}

def _atomic_write(path, text):
    """temp->rename: a re-run that times out can't partially clobber an already-good file.

    Write to .tmp, then os.replace (atomic within a filesystem). If the process dies
    mid-write, the previous valid file stays in place rather than a truncated one."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main():
    argv = sys.argv[1:]
    pos = [a for a in argv if not a.startswith("-")]
    flags = [a for a in argv if a.startswith("-")]
    topic = pos[0] if pos else "topic1"
    qfile = pos[1] if len(pos) > 1 else None
    only = pos[2].split(",") if len(pos) > 2 else None
    skip_ok = "--skip-ok" in flags
    force = "--force" in flags
    min_ok = 1
    for f in flags:
        if f.startswith("--min-ok="):
            min_ok = int(f.split("=", 1)[1])
    if not qfile:
        print("usage: engines.py <topic> <question_file> [eng1,eng2] [--skip-ok] [--force] [--min-ok=N]",
              file=sys.stderr)
        sys.exit(64)

    # selected engines actually exist (a typo in the list -> clear error, not an empty executor)
    if only:
        bad = [e for e in only if e not in ENGINES]
        if bad:
            print(f"✗ unknown engines: {bad}. Available: {', '.join(ENGINES)}", file=sys.stderr)
            sys.exit(2)

    q = pathlib.Path(qfile).read_text()
    P.engines_dir(topic).mkdir(parents=True, exist_ok=True)
    P.question(topic).write_text(q)

    # run intent = the full set of selected engines (denominator of the post-check)
    intended = {k: v for k, v in ENGINES.items() if (only is None or k in only)}

    # --skip-ok: don't re-run engines that already have a good report (--force overrides)
    import engine_status as ES
    to_run = dict(intended)
    if skip_ok and not force:
        kept = {}
        for name, fn in intended.items():
            if ES.status_for_file(P.engine_raw(topic, name)) == "ok":
                print(f"  ⏭ {name}: already ok — skipping (--skip-ok)")
            else:
                kept[name] = fn
        to_run = kept

    print(f"topic={topic}, to run={len(to_run)}/{len(intended)}: {', '.join(to_run) or '—'}")
    if to_run:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(to_run)) as ex:
            futs = {ex.submit(fn, q): name for name, fn in to_run.items()}
            for fut in concurrent.futures.as_completed(futs):
                name = futs[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"error": f"{type(e).__name__}: {e}"}
                _atomic_write(P.engine_raw(topic, name), json.dumps(res, ensure_ascii=False, indent=2))
                if res.get("error"):
                    print(f"  ✗ {name}: {res['error']}")
                else:
                    print(f"  ✓ {name}: {len(res.get('report',''))} chars, "
                          f"{len(res.get('sources',[]))} links, ≈${res.get('cost_est')}, {res.get('seconds')}s")
    print("saved to", P.engines_dir(topic))

    # ── post-check: how many engines are actually usable (over the full intended set) ──
    audit = ES.audit_topic(topic, list(intended.keys()))
    usable = ES.print_summary(topic, audit)
    if usable < min_ok:
        print(f"✗ usable engines {usable} < threshold {min_ok} — do NOT run atomize/check_claims. "
              f"Re-run the failed ones (engines.py {topic} <q> {','.join(intended)} --skip-ok).", file=sys.stderr)
        sys.exit(2)
    if usable < len(intended):
        print(f"⚠ some engines dropped ({usable}/{len(intended)} usable) — coverage reduced, but threshold passed.")


if __name__ == "__main__":
    main()
