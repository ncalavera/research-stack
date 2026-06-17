#!/usr/bin/env python3
"""Soft prose guard: checks that all numbers in narratives are taken from pool facts.

Problem: Opus sometimes inserts numbers into prose that are not in the confirmed facts —
roundings, adjacent values, paraphrases. This script catches such discrepancies.

Architecture:
- Reads narratives: from narratives_file in config or narratives-<topic>.json.
- Extracts ALL numeric tokens from string values in narratives (all sections, _keypoints,
  _tables, _so_what, _action_plan, _infographic, etc.)
- Builds the "allowed set" from three sources:
    1. Fact texts + corrected field in judge_claims/pool/<topic>.json
    2. String values in reports/<topic>.config.json (titles may carry numbers)
    3. Strings in facts/<topic>.json (sub-questions may quote user numbers)
- Whitelist for lone digits 0–3 and list markers (1., 2., etc.) — excluded from check.
  Years 1900–2100 are NOT whitelisted — checked as well.
- Normalization: remove thousands separators, normalize both hyphen/dash variants in ranges to "-",
  decimal comma to period.
- Output: exit 0 — clean; exit 2 — violations found (SOFT gate: warning, not a block).

Usage: python3 funnel/prose_gate.py <topic>
"""
import sys
import re
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

# ── number normalization ──────────────────────────────────────────────────────

# Replaces thousands separators (space, non-breaking space, EN thousands comma)
_THOU_RE = re.compile(r'(\d)[  ](\d{3})')

# Main pattern: range (via hyphen/dash) or single number
# Catches: 1.6–2.2, 1,6-2,2, 7, 2500, 75%, $100, 0.8–1.2
_NUM_RE = re.compile(
    r'[\$€₽]?'                          # optional currency
    r'(\d+(?:[.,]\d+)?)'               # first number (integer or decimal)
    r'(?:\s*[–—\-]\s*(\d+(?:[.,]\d+)?))?'  # optional range end
    r'(?:\s*%)?'                       # optional percent
)


def _norm_num(s: str) -> str:
    """Normalizes a number string: decimal comma → period, remove thousands separators."""
    s = s.replace(',', '.')
    return s


def _norm_token(tok: str) -> str:
    """Normalizes a numeric token for comparison.
    Ranges stored as "<lo>-<hi>", single numbers — as string with period instead of comma.
    """
    # remove currency signs and %
    tok = tok.strip().lstrip('$€₽').rstrip('%').strip()
    # replace em-dash and en-dash with regular hyphen
    tok = tok.replace('–', '-').replace('—', '-')
    # remove spaces around hyphen
    tok = re.sub(r'\s*-\s*', '-', tok)
    # decimal comma → period
    # but only when comma separates digits
    tok = re.sub(r'(\d),(\d)', r'\1.\2', tok)
    # remove thousands separators (space before triple digits)
    while re.search(r'\d[  ]\d{3}', tok):
        tok = re.sub(r'(\d)[  ](\d{3})', r'\1\2', tok)
    return tok


def extract_numbers(text: str) -> list[tuple[str, str]]:
    """Extracts numeric tokens from a string.
    Returns list of (raw_token, normalized_token).
    Whitelist: lone digits 0–3 and "N." markers are excluded.
    """
    # citation elements <a ...>...</a> — provenance, not prose claims:
    # arXiv IDs, years and article IDs in link text are not checked against the pool
    text = re.sub(r'<a\s[^>]*>.*?</a>', ' ', text, flags=re.DOTALL)
    results = []
    for m in _NUM_RE.finditer(text):
        raw = m.group(0).strip()
        if not raw or not re.search(r'\d', raw):
            continue
        norm = _norm_token(raw)
        # whitelist: lone digits 0, 1, 2, 3
        if re.fullmatch(r'[0-3]', norm):
            continue
        # whitelist: list markers — lone digit or "N." without additional context
        # Check: number is at the start of a line as "1. " or "2) "
        start = m.start()
        before = text[max(0, start-1):start]
        after = text[m.end():m.end()+2]
        if re.fullmatch(r'\d{1,2}', norm) and (before in ('', '\n', ' ', '\t') or not before) and re.match(r'[.)]\s', after):
            continue
        results.append((raw, norm))
    return results


def _strings_from(obj) -> list[str]:
    """Recursively collects all string values from a JSON object."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, list):
        result = []
        for item in obj:
            result.extend(_strings_from(item))
        return result
    if isinstance(obj, dict):
        result = []
        for v in obj.values():
            result.extend(_strings_from(v))
        return result
    return []


def _strings_with_key(obj, prefix='') -> list[tuple[str, str]]:
    """Recursively collects (key, string_value) from a JSON object."""
    results = []
    if isinstance(obj, str):
        results.append((prefix, obj))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(_strings_with_key(item, f'{prefix}[{i}]'))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            child_key = f'{prefix}.{k}' if prefix else k
            results.extend(_strings_with_key(v, child_key))
    return results


def build_allowed_set(topic: str) -> set[str]:
    """Builds the set of allowed normalized numeric tokens from three sources:
    1. topics/<topic>/pool.json — fact texts + corrected field
    2. topics/<topic>/config.json — config string values
    3. topics/<topic>/facts.json — sub-question strings
    """
    allowed: set[str] = set()

    # 1. Fact pool
    pool_path = P.pool(topic)
    if pool_path.exists():
        pool = json.loads(pool_path.read_text('utf-8'))
        for f in pool.get('facts', []):
            for s in _strings_from(f.get('text', '')):
                for _, norm in extract_numbers(s):
                    allowed.add(norm)
            corrected = f.get('corrected', '')
            if corrected:
                for _, norm in extract_numbers(str(corrected)):
                    allowed.add(norm)
            # provenance corrected
            for p in f.get('provenance', []):
                pc = p.get('corrected', '')
                if pc:
                    for _, norm in extract_numbers(str(pc)):
                        allowed.add(norm)

    # 2. Topic config
    cfg_path = P.config(topic)
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text('utf-8'))
        for s in _strings_from(cfg):
            for _, norm in extract_numbers(s):
                allowed.add(norm)

    # 3. topics/<topic>/facts.json
    facts_path = P.facts(topic)
    if facts_path.exists():
        facts_data = json.loads(facts_path.read_text('utf-8'))
        for s in _strings_from(facts_data):
            for _, norm in extract_numbers(s):
                allowed.add(norm)

    return allowed


def check_prose(topic: str) -> list[dict]:
    """Main function: returns list of violations — numbers in narratives outside the allowed set.
    Each violation: {'key': str, 'number': str, 'snippet': str}
    """
    # Determine narratives file
    narr_path = None
    cfg_path = P.config(topic)
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text('utf-8'))
        narr_file = cfg.get('narratives_file', '')
        if narr_file:
            candidate = ROOT / narr_file
            if candidate.exists():
                narr_path = candidate
    if narr_path is None:
        fallback = P.narratives(topic)
        if fallback.exists():
            narr_path = fallback

    if narr_path is None:
        return None  # no narratives — skip (signal to caller)

    narr = json.loads(narr_path.read_text('utf-8'))
    allowed = build_allowed_set(topic)

    violations = []
    # Walk all string values in narratives
    for key, text in _strings_with_key(narr):
        # Skip system meta keys
        if key in ('_meta',):
            continue
        nums = extract_numbers(text)
        for raw, norm in nums:
            if norm not in allowed:
                # Build snippet ~80 chars around the occurrence
                idx = text.find(raw)
                if idx == -1:
                    snippet = text[:80]
                else:
                    start = max(0, idx - 30)
                    end = min(len(text), idx + len(raw) + 50)
                    snippet = ('…' if start > 0 else '') + text[start:end] + ('…' if end < len(text) else '')
                violations.append({'key': key, 'number': raw, 'norm': norm, 'snippet': snippet})

    return violations


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else None
    if not topic:
        print('topic required: python3 funnel/prose_gate.py <topic>')
        sys.exit(2)

    violations = check_prose(topic)

    if violations is None:
        print(f'no narratives — draft, prose not checked')
        sys.exit(0)

    if not violations:
        print(f'✓ prose: numbers in narratives match the fact pool')
        sys.exit(0)

    print(f'⚠ PROSE: {len(violations)} number(s) in narratives not in fact pool (soft gate):')
    for v in violations:
        print(f'  [{v["key"]}] {v["number"]!r} → «{v["snippet"]}»')
    sys.exit(2)


if __name__ == '__main__':
    main()
