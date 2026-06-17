#!/usr/bin/env bash
# Fetch one URL for the blind judge: UA → r.jina.ai → Firecrawl.
# Prints page text to stdout. Exit 0 — something retrieved, 1 — link is dead/unavailable.
# Usage: ./fetch_url.sh "https://..."
set -uo pipefail
URL="${1:?usage: fetch_url.sh <url>}"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# ─── Disk cache by URL (reuse across engines/runs) ───
# One page (gov.uk etc.) is cited by dozens of claims across 6 engines — fetch once.
# Only cache SUCCESS (exit 0); dead links are not cached (they can come back via re-sourcing).
# Lives in the repo root, not in a worktree copy — survives worktree cleanup.
CACHE_DIR="$(dirname "$0")/.fetch_cache"
KEY=$(printf '%s' "$URL" | shasum -a 1 | cut -d' ' -f1)
CACHE="$CACHE_DIR/$KEY"
if [[ -f "$CACHE" ]]; then
  cat "$CACHE"; exit 0
fi
mkdir -p "$CACHE_DIR" 2>/dev/null

# Gemini vertexaisearch redirects are unauditable (methodology §7) — immediately dead.
if [[ "$URL" == *"vertexaisearch"* || "$URL" == *"grounding-api-redirect"* ]]; then
  echo "__UNAUDITABLE__ vertexaisearch redirect"; exit 1
fi

# YouTube: the page returns only the menu — a transcript is needed. Delegate to fetch_youtube.sh.
if [[ "$URL" == *"youtube.com/watch"* || "$URL" == *"youtu.be/"* || "$URL" == *"youtube.com/shorts/"* ]]; then
  exec "$(dirname "$0")/fetch_youtube.sh" "$URL"
fi

# 0.5) Scientific links: PubMed returns only the abstract; paywalled publishers return a landing page.
# Fetch the full text legally via Europe PMC / Unpaywall (resolve_oa.py) BEFORE the normal fetch.
# pmc.ncbi (already OA) goes through the normal path — it is fast and full-text on its own.
if [[ "$URL" =~ (pubmed\.ncbi\.nlm\.nih\.gov|//doi\.org/|link\.springer\.com|sciencedirect\.com|onlinelibrary\.wiley\.com|tandfonline\.com|nature\.com|journals\.lww\.com|academic\.oup\.com) ]]; then
  OA=$("$(dirname "$0")/resolve_oa.py" "$URL" 2>/dev/null)
  if [[ $? -eq 0 && -n "$OA" ]]; then
    printf '%s\n' "$OA" | tee "$CACHE" 2>/dev/null; exit 0
  fi
fi

# ─── Generic challenge-wall detector ───
# Anti-bot/JS-SPA shells (Cloudflare "Just a moment", reCAPTCHA, Salesforce "CSS Error")
# pass the naive length threshold and replace content → the judge sees a wall and falsely marks BROKEN.
# gate() reads text from stdin, prints it if usable; otherwise exit 3 (needs escalation).
gate() {  # argument: method label (for logging)
  python3 -c "
import sys
t = sys.stdin.read().strip()
low = t[:1200].lower()  # walls shout at the start of the document
WALL = ['checking your browser', 'recaptcha', 'just a moment',
        'enable javascript', 'css error', 'sorry to interrupt',
        'verify you are human', 'performing security verification',
        'security verification', 'access denied', 'attention required',
        'target url returned error 403', 'requiring captcha']
hit = any(w in low for w in WALL)
# wall: empty/too short, OR wall marker at the start and document is small (real articles are long)
if len(t) < 350 or (hit and len(t) < 6000):
    sys.exit(3)
print(t[:45000])
"
}

# emit: prints the successful result AND places it in the URL cache. Args: text, __SOURCE__ marker line.
emit() {
  { printf '%s\n' "$1"; printf '%s\n' "$2"; } | tee "$CACHE" 2>/dev/null
  exit 0
}

strip_html() {  # stdin: HTML → plain text
  python3 -c "import sys,re,html; t=sys.stdin.read(); t=re.sub(r'<script.*?</script>','',t,flags=re.S|re.I); t=re.sub(r'<style.*?</style>','',t,flags=re.S|re.I); t=re.sub(r'<[^>]+>',' ',t); t=html.unescape(t); t=re.sub(r'\s+',' ',t); print(t)"
}

# 1) Direct request with browser UA.
BODY=$(curl -sL --max-time 25 -A "$UA" "$URL" 2>/dev/null)
CODE=$(curl -sL --max-time 25 -A "$UA" -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null)
if [[ -n "$BODY" && "$CODE" =~ ^2 ]]; then
  TXT=$(echo "$BODY" | strip_html | gate)
  if [[ $? -eq 0 && -n "$TXT" ]]; then
    emit "$TXT" "__SOURCE__ direct http=$CODE len=${#TXT}"
  fi
fi

# 2) r.jina.ai — clean markdown via proxy reader.
J=$(curl -sL --max-time 30 -A "$UA" "https://r.jina.ai/$URL" 2>/dev/null)
JT=$(echo "$J" | gate)
if [[ $? -eq 0 && -n "$JT" ]]; then
  emit "$JT" "__SOURCE__ jina len=${#JT}"
fi

# Firecrawl branch: JSON → markdown → same gate.
extract_md() {  # input: Firecrawl JSON in $1
  echo "$1" | python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('__BADJSON__'); sys.exit(3)
if not d.get('success'): print('__FCERR__ '+(d.get('error') or '')[:120]); sys.exit(3)
print(((d.get('data') or {}).get('markdown') or '').strip())" | gate
}

fc_scrape() {  # $1=url $2=extra-json (proxy/waitFor) $3=timeout; prints JSON
  curl -s --max-time "${3:-50}" -X POST https://api.firecrawl.dev/v1/scrape \
    -H "Authorization: Bearer $FIRECRAWL_API_KEY" -H "Content-Type: application/json" \
    -d "{\"url\":\"$1\",\"formats\":[\"markdown\"],\"onlyMainContent\":true$2}" 2>/dev/null
}

if [[ -n "${FIRECRAWL_API_KEY:-}" ]]; then
  # 3) Firecrawl basic scrape (cheap) with retry on 429.
  for attempt in 1 2; do
    FC=$(fc_scrape "$URL" "" 50)
    if echo "$FC" | grep -q '"statusCode":429\|[Rr]ate limit'; then
      sleep $((attempt * 4)); continue   # 429: back-off and retry
    fi
    break
  done
  MD=$(extract_md "$FC")
  if [[ $? -eq 0 && -n "$MD" ]]; then
    emit "$MD" "__SOURCE__ firecrawl len=${#MD}"
  fi

  # 4) Firecrawl STEALTH + waitFor — last resort against Cloudflare/reCAPTCHA/JS-SPA.
  # More expensive in credits, so only used when everything above hit a wall.
  FCS=$(fc_scrape "$URL" ",\"proxy\":\"stealth\",\"waitFor\":4000" 100)
  MDS=$(extract_md "$FCS")
  if [[ $? -eq 0 && -n "$MDS" ]]; then
    emit "$MDS" "__SOURCE__ firecrawl_stealth len=${#MDS}"
  fi
fi

echo "__DEAD__ direct_http=$CODE — link unavailable (UA→jina→firecrawl→stealth)"; exit 1
