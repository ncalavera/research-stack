#!/usr/bin/env python3
"""Gate tests: verify that contracts catch violations, not pass them.

Usage: python3 funnel/test_funnel.py
Positive tests — on live data from topic1 (committed). Negative tests — on fabricated
bad facts: the guard MUST reject them, otherwise the guarantee does not hold.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import contracts as C
from contracts import StageError

ok, fail = 0, 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}")


print("Positive (build topic1 in memory, no file writes):")
import build_pool as B
_v = B.load_verdicts("topic1")
_conf, _unconf = B.split(_v)
_all = _conf + B.load_resourced("topic1")
_facts = [f for f in (B.to_fact(c["items"], {}) for c in B.cluster(_all)) if f]
check("topic1 verdicts valid", C.validate_verdicts("topic1") >= 6)
check("topic1 pool assembled, facts present", len(_facts) > 0)
check("each fact has fid + anchor_id", all(f.get("fid") and f.get("anchor_id") for f in _facts))
check("guard passes freshly built topic1 pool (text=anchor by construction)",
      C.offenders_in(_facts) == [])

print("\nNegative (guard must reject):")
U = "https://iea.org/x"
TXT = "Renewable energy delivers sustained capacity growth."
def anchor(**kw):
    a = {"label": "SUPPORTED", "source": U, "source_alive": True, "text": TXT}
    a.update(kw)
    return a
def fact(text=TXT, prov=None, best=U):
    return {"text": text, "provenance": prov if prov is not None else [anchor()], "best_source": best}

check("clean fact (text=anchor) passes", C.offenders_in([fact()]) == [])
# main Codex attack: text rewritten, link is live — must be rejected
check("REWRITTEN text under live link — rejected (gap #2)",
      C.offenders_in([fact(text="A completely different claim about anything")]))
check("fact without live backing (UNSOURCED) — rejected",
      C.offenders_in([fact(prov=[{"label": "UNSOURCED", "source": "", "text": TXT}])]))
check("fabricated fact — rejected",
      C.offenders_in([fact(prov=[anchor(fabricated=True)])]))
check("dead source under SUPPORTED — rejected (gap #1)",
      C.offenders_in([fact(prov=[anchor(source_alive=False)])]))
check("source_alive absent (recovered without flag) — rejected (Codex gap #4)",
      C.offenders_in([fact(prov=[{"label": "SUPPORTED", "source": U, "text": TXT}])]))
check("strict anchor with corrected in provenance, but no fact.corrected — rejected (no verified badge)",
      C.offenders_in([fact(prov=[anchor(corrected="7 hours")])]))
check("non-URL backing 'see above' — rejected",
      C.offenders_in([fact(prov=[anchor(source="see above")], best="see above")]))
check("best_source not a URL — rejected",
      C.offenders_in([fact(best="N/A")]))

print("\nAnchors with corrected number (corrected anchor):")
CORRVAL = "7 years"

def corrected_anchor(**kw):
    a = {"label": "PARTIAL", "source": U, "source_alive": True, "text": TXT, "corrected": CORRVAL}
    a.update(kw)
    return a

def corrected_fact(text=TXT, corr=CORRVAL, prov=None, best=U):
    return {"text": text, "corrected": corr,
            "provenance": prov if prov is not None else [corrected_anchor()],
            "best_source": best}

# (a) corrected anchor + matching fact.corrected → passes
check("(a) corrected anchor + matching fact.corrected → passes",
      C.offenders_in([corrected_fact()]) == [])

# (b) corrected anchor + fact.corrected absent → rejected
check("(b) corrected anchor + fact.corrected absent → rejected",
      C.offenders_in([{"text": TXT, "provenance": [corrected_anchor()], "best_source": U}]))

# (c) corrected anchor + fact.corrected does not match → rejected
check("(c) corrected anchor + fact.corrected mismatch → rejected",
      C.offenders_in([corrected_fact(corr="8 years")]))

# (d) strict anchor + stray fact.corrected → rejected (badge without verification)
check("(d) strict anchor + stray fact.corrected → rejected",
      C.offenders_in([{"text": TXT, "corrected": "7 years",
                       "provenance": [anchor()], "best_source": U}]))

# (e) build_pool.to_fact prefers strict anchor when both present; corrected=None
_strict = {"label": "SUPPORTED", "source": U, "source_alive": True,
           "text": TXT, "corrected": None, "fabricated": False,
           "engine": "exa", "src_key": "exa", "id": "1",
           "class": "A", "confidence": "high", "has_number": False}
_corr_item = {"label": "PARTIAL", "source": U, "source_alive": True,
              "text": TXT, "corrected": CORRVAL, "fabricated": False,
              "engine": "perp", "src_key": "perp", "id": "2",
              "class": "B", "confidence": "medium", "has_number": True}
_f_prefer = B.to_fact([_strict, _corr_item], {})
check("(e) to_fact prefers strict anchor when both in cluster; corrected=None",
      _f_prefer is not None and _f_prefer.get("corrected") is None)

print("\nTraceability check (manual insertion bypassing — soft signal):")
known = {U}
check("fact with source from verdicts — traceable",
      C.orphans_in([fact()], known) == [])
check("fact with source NOT from verdicts — flagged",
      C.orphans_in([{"provenance": [{"source": "https://evil.example/inject"}],
                     "best_source": "https://evil.example/inject"}], known))
# freshly built topic1: sources are traceable to verdicts+re-sourcing (soft signal)
_known = C.verdict_sources("topic1")
check("topic1: fresh pool traceability is normal (soft signal)",
      len(C.orphans_in(_facts, _known)) <= 10)

print("\nOrder cannot be broken (input missing → refusal):")
try:
    C.validate_raw("topic_nonexistent_xyz")
    check("early access to non-existent raw fails", False)
except StageError:
    check("early access to non-existent raw fails", True)

print("\nProse guard (prose_gate):")
import prose_gate as PG

# Helper function: build minimal allowed set in memory
def _check_prose(narr_strings: list[str], allowed_strings: list[str]) -> list[dict]:
    """Test wrapper: catches numbers in narr_strings that are not in allowed_strings."""
    import re
    allowed: set[str] = set()
    for s in allowed_strings:
        for _, norm in PG.extract_numbers(s):
            allowed.add(norm)
    violations = []
    for i, text in enumerate(narr_strings):
        for raw, norm in PG.extract_numbers(text):
            if norm not in allowed:
                violations.append({'key': f'test[{i}]', 'number': raw, 'norm': norm, 'snippet': text[:80]})
    return violations

# Test 1: clean narrative — all numbers are in the pool
_pool_text_1 = "Global installed solar capacity reached 1.2–1.6 TW by 2024."
_narr_text_1 = "According to data, the solar capacity range is 1.2–1.6 TW."
check("prose: clean narrative (all numbers in pool) → no violations",
      _check_prose([_narr_text_1], [_pool_text_1]) == [])

# Test 2: narrative with a number not in the pool → violation
_narr_text_2 = "Studies show 10 TW of installed capacity."
check("prose: number 10 absent from pool → violation found",
      len(_check_prose([_narr_text_2], [_pool_text_1])) > 0)

# Test 3: range normalization — "1,6–2,2" and "1.6-2.2" are the same
_pool_text_3 = "Wind utilization factor: 1.6-2.2 depending on region."
_narr_text_3 = "The factor is 1,6–2,2 across regions."
check("prose: range normalization (1,6–2,2 == 1.6-2.2) → no violations",
      _check_prose([_narr_text_3], [_pool_text_3]) == [])

# Test 4: numbers from the corrected field are allowed
_allowed_strings_4 = []  # no direct fact text
_corrected_val = "7 years"
# build allowed from corrected directly
_allowed_4: set[str] = set()
for _, n in PG.extract_numbers(_corrected_val):
    _allowed_4.add(n)
_narr_text_4 = "The payback period is 7 years."
_viols_4 = []
for raw, norm in PG.extract_numbers(_narr_text_4):
    if norm not in _allowed_4:
        _viols_4.append(norm)
check("prose: number from corrected field is allowed → no violations",
      _viols_4 == [])

print("\nPartition_facts (render-level, helper extracted without executing render main):")
# Extract partition_facts from render_final.py without importing the module
# (render_final.py runs at module level: reads pool JSON, writes HTML — unsafe to import directly)
import io, types
_render_src = (pathlib.Path(__file__).resolve().parent.parent / "render_final.py").read_text("utf-8")
# grab only lines up to and including partition_facts (ends at the blank line after its closing 'pass')
_end_marker = "\ndef load(path, default):"
_cut = _render_src.index(_end_marker)
_snippet = (
    "import json, pathlib, sys\n"
    + _render_src[:_cut]
    + "\n"
)
_render_path = str(pathlib.Path(__file__).resolve().parent.parent / "render_final.py")
_ns = {"__file__": _render_path}
exec(compile(_snippet, "render_final_helpers", "exec"), _ns)
_partition_facts = _ns["partition_facts"]

# Test 1: happy path — grouping works, grouped fids absent from standalone
_facts_pt = [{"fid": "aa"}, {"fid": "bb"}, {"fid": "cc"}]
_ct_data = {"groups": [{"gid": "g1", "issue": "X", "fids": ["aa", "bb"]}]}
import io as _io, contextlib as _cl
_out = _io.StringIO()
with _cl.redirect_stdout(_out):
    _standalone, _groups = _partition_facts(_facts_pt, _ct_data)
check("partition: grouping works — aa+bb grouped, cc standalone",
      _groups == [{"gid": "g1", "issue": "X", "fids": ["aa", "bb"]}]
      and _standalone == {"cc"})

# Test 2: unknown fid → warning printed, group with <2 valid fids degrades to standalone
_ct_bad = {"groups": [{"gid": "g2", "issue": "Y", "fids": ["aa", "UNKNOWN_FID"]}]}
_out2 = _io.StringIO()
with _cl.redirect_stdout(_out2):
    _standalone2, _groups2 = _partition_facts(_facts_pt, _ct_bad)
check("partition: unknown fid → warning printed",
      "UNKNOWN_FID" in _out2.getvalue())
check("partition: group with <2 valid fids degrades — all standalone, no groups",
      _groups2 == [] and _standalone2 == {"aa", "bb", "cc"})

print("\nFeature 1: quote field pass-through:")
_q_item = {"label": "SUPPORTED", "source": U, "source_alive": True,
           "text": TXT, "corrected": None, "fabricated": False,
           "engine": "exa", "src_key": "exa", "id": "q1",
           "class": "A", "confidence": "high", "has_number": False,
           "quote": "Renewable energy delivers sustained capacity growth on a global scale."}
_q_fact = B.to_fact([_q_item], {})
check("quote preserved through to_fact",
      _q_fact is not None and _q_fact.get("quote") == "Renewable energy delivers sustained capacity growth on a global scale.")

check("quote=None in fact when absent in anchor",
      B.to_fact([_strict], {}) is not None and B.to_fact([_strict], {}).get("quote") is None)

print("\nFeature 1: quote_block HTML escaping:")
import re as _re
_render_src2 = (pathlib.Path(__file__).resolve().parent.parent / "render_final.py").read_text("utf-8")
_qb_match = _re.search(r'(def quote_block\(.*?\n(?:    .*\n)+)', _render_src2)
if _qb_match:
    _qb_src = ("import html\ndef esc(t):\n    return html.escape(str(t))\n"
               "def src_link(url, paren=True):\n    return url\n"
               + _qb_match.group(1))
    _qb_ns = {}
    exec(compile(_qb_src, "qb_helper", "exec"), _qb_ns)
    _qb = _qb_ns["quote_block"]
    check("quote_block escapes HTML in quote text",
          "&lt;" in _qb("<script>alert(1)</script>", None))
    check("quote_block returns empty string for None/empty quote",
          _qb(None, None) == "" and _qb("", None) == "")
else:
    check("quote_block function found in render_final.py", False)
    check("quote_block returns empty for None", False)

print("\nFeature 2: stances in contradiction groups:")
_ct_stances = {"groups": [{"gid": "g3", "issue": "Z", "fids": ["aa", "bb"],
                            "stances": {"aa": "поддерживает", "bb": "опровергает", "UNKNOWN": "смешанно"}}]}
_out3 = _io.StringIO()
with _cl.redirect_stdout(_out3):
    _standalone3, _groups3 = _partition_facts(_facts_pt, _ct_stances)
check("stances: group with stances is valid (aa+bb grouped)",
      len(_groups3) == 1 and _groups3[0]["fids"] == ["aa", "bb"])
check("stances: unknown fid in stances doesn't cause error (cc standalone)",
      "cc" in _standalone3)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
