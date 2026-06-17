#!/usr/bin/env bash
# Fetch a YouTube TRANSCRIPT for fact-checking: yt-dlp auto-subtitles → plain text.
# Without a transcript a YouTube link is unauditable (returns only the menu) — the judge correctly marks the fact as misattributed.
# With a transcript the claim is checked against what was actually said in the video.
# Prints text to stdout. Exit 0 — transcript retrieved, 1 — not available (no subtitles / private video).
# Usage: ./fetch_youtube.sh "https://www.youtube.com/watch?v=..."
set -uo pipefail
URL="${1:?usage: fetch_youtube.sh <youtube-url>}"
TMP="$(mktemp -d /tmp/yt_tr.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# json3 auto-subtitles → plain text
to_text() {
  python3 -c "
import json,glob,sys,re
f=glob.glob('$TMP/*.json3')
if not f: sys.exit(1)
d=json.load(open(f[0]))
out=[]
for ev in d.get('events',[]):
    for s in ev.get('segs',[]) or []:
        t=s.get('utf8','')
        if t.strip(): out.append(t)
txt=re.sub(r'\s+',' ',''.join(out)).strip()
if len(txt)<200: sys.exit(1)
print(txt[:45000])
"
}

# 1) attempt in priority order: English/Russian (majority of research videos)
pull() { # $1 = sub-langs
  yt-dlp --no-update --quiet --skip-download --write-auto-subs --write-subs \
         --sub-langs "$1" --sub-format json3 -o "$TMP/s.%(ext)s" "$URL" >/dev/null 2>&1
}

pull "en.*,ru.*"
TXT="$(to_text 2>/dev/null)"

# 2) fallback: original video language (first auto-track from the list)
if [[ -z "$TXT" ]]; then
  rm -f "$TMP"/*.json3 2>/dev/null
  LANG0="$(yt-dlp --no-update --skip-download --list-subs "$URL" 2>/dev/null \
           | awk '/Available automatic captions/{f=1;next} f&&NF&&$1!="Language"{print $1; exit}')"
  if [[ -n "$LANG0" ]]; then
    pull "$LANG0"
    TXT="$(to_text 2>/dev/null)"
  fi
fi

if [[ -n "$TXT" ]]; then
  echo "$TXT"
  echo; echo "__SOURCE__ youtube-transcript len=${#TXT}"; exit 0
fi

echo "__DEAD__ youtube — no subtitles/transcript unavailable"; exit 1
