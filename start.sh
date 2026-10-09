#!/usr/bin/env bash
# Start Voice Studio: UI and API at http://localhost:8765 (VOICER_PORT changes the port).
#   ./start.sh          run in this terminal (Ctrl+C stops it)
#   ./start.sh --open   also open the UI in the browser (under WSL: the Windows browser)
# If it is already running, it only opens the UI (with --open).
set -euo pipefail
cd "$(dirname "$0")"

OPEN=0
for a in "$@"; do
  case "$a" in
    --open) OPEN=1 ;;
    -h|--help) sed -n '2,5s/^# \{0,1\}//p' "$0"; exit 0 ;;
    *) echo "Unknown option: $a (see ./start.sh --help)" >&2; exit 2 ;;
  esac
done

[ -x .venv/bin/python ] || { echo "Voice Studio is not installed yet. Run ./install.sh first." >&2; exit 1; }
URL="http://localhost:${VOICER_PORT:-8765}"

up() {
  .venv/bin/python -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)' "$URL/api/health" 2>/dev/null
}

open_ui() {
  if [ -n "${VOICER_BROWSER:-}" ]; then
    "$VOICER_BROWSER" "$URL"
  elif grep -qi microsoft /proc/version 2>/dev/null && command -v cmd.exe >/dev/null; then
    (cd /mnt/c 2>/dev/null || true; cmd.exe /c start "" "$URL" >/dev/null 2>&1)
  elif command -v xdg-open >/dev/null; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  else
    echo "Open $URL in your browser."
  fi
}

if up; then
  echo "Voice Studio is already running at $URL"
  [ "$OPEN" = 1 ] && open_ui
  exit 0
fi

if [ "$OPEN" = 1 ]; then
  (for _ in $(seq 120); do sleep 1; if up; then open_ui; exit 0; fi; done
   echo "Voice Studio did not start within 2 minutes." >&2) &
fi
echo "Starting Voice Studio at $URL (Ctrl+C stops it)"
exec .venv/bin/python -m voicer
