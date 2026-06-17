#!/usr/bin/env bash
# Build a PDF from a finished HTML report via headless Chrome (@media print styles).
# Usage: ./render_pdf.sh [reports/REPORT-topic1.html]
set -euo pipefail
cd "$(dirname "$0")"

HTML="${1:-reports/REPORT-topic1.html}"
PDF="${HTML%.html}.pdf"
ABS="file://$(cd "$(dirname "$HTML")" && pwd)/$(basename "$HTML")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

[ -f "$HTML" ] || { echo "file not found: $HTML — run python3 render_final.py first"; exit 1; }
[ -x "$CHROME" ] || { echo "Google Chrome not found"; exit 1; }

"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
  --virtual-time-budget=8000 \
  --print-to-pdf="$PDF" "$ABS" 2>/dev/null

echo "done: $PDF ($(du -h "$PDF" | cut -f1))"
