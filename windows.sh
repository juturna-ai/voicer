#!/usr/bin/env bash
# Windows shortcuts for Voice Studio (run inside WSL).
#   ./windows.sh shortcut          "Voice Studio" icon on the Windows desktop: starts the server, opens the UI
#   ./windows.sh remove-shortcut   remove that icon
#   ./windows.sh autostart on      start the server when you sign in to Windows (no browser)
#   ./windows.sh autostart off     stop doing that
# The server runs in a minimized window; close that window to stop Voice Studio.
# VOICER_PORT / VOICER_DATA / VOICER_BROWSER, if set now, are kept in the shortcut.
set -euo pipefail
cd "$(dirname "$0")"
NAME="Voice Studio"

usage() { sed -n '2,8s/^# \{0,1\}//p' "$0"; }
die() { echo "$*" >&2; exit 1; }

grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe >/dev/null \
  || die "This works only inside WSL on Windows."
[ -x start.sh ] || die "start.sh is missing."

ps() {   # run PowerShell from a Windows folder (no UNC-path warning); strip CR
  (cd /mnt/c && powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$1") | tr -d '\r'
}
q() { printf "'%s'" "${1//\'/\'\'}"; }       # PowerShell single-quoted string

folder() {   # $1 = Desktop | Startup; VOICER_DESKTOP / VOICER_STARTUP (Windows paths) override, for tests
  local var="VOICER_${1^^}"
  if [ -n "${!var:-}" ]; then echo "${!var}"; else ps "[Environment]::GetFolderPath('$1')"; fi
}

args() {     # $@ = start.sh options → wsl.exe arguments
  local envs=() v
  for v in VOICER_PORT VOICER_DATA VOICER_BROWSER; do
    [ -n "${!v:-}" ] && envs+=("$v='${!v//\'/}'")
  done
  local cmd="./start.sh${*:+ $*}"
  [ ${#envs[@]} -gt 0 ] && cmd="env ${envs[*]} $cmd"
  printf -- '-d %s --cd "%s" -- %s' "${WSL_DISTRO_NAME:?not in WSL}" "$PWD" "$cmd"
}

make_link() {   # $1 = folder, $2 = arguments, $3 = window style (1 normal, 7 minimized)
  local path="$1\\$NAME.lnk"
  ps "\$s = (New-Object -ComObject WScript.Shell).CreateShortcut($(q "$path"));
      \$s.TargetPath = \"\$env:SystemRoot\\System32\\wsl.exe\"; \$s.Arguments = $(q "$2");
      \$s.WorkingDirectory = \$env:USERPROFILE; \$s.WindowStyle = $3;
      \$s.Description = 'Voice Studio: start the server and open the UI'; \$s.Save(); \$s.FullName"
}

remove_link() {
  local path="$1\\$NAME.lnk"
  ps "if (Test-Path -LiteralPath $(q "$path")) { Remove-Item -LiteralPath $(q "$path"); 'removed' } else { 'none' }"
}

case "${1:-}" in
  shortcut)
    out=$(make_link "$(folder Desktop)" "$(args --open)" 7)
    echo "Desktop shortcut made: $out"
    echo "Double-click it to start Voice Studio and open http://localhost:${VOICER_PORT:-8765}" ;;
  remove-shortcut)
    [ "$(remove_link "$(folder Desktop)")" = removed ] && echo "Desktop shortcut removed." || echo "There was no desktop shortcut." ;;
  autostart)
    case "${2:-}" in
      on)
        out=$(make_link "$(folder Startup)" "$(args)" 7)
        echo "Auto-start is on: $out"
        echo "Voice Studio starts (minimized) each time you sign in to Windows." ;;
      off)
        [ "$(remove_link "$(folder Startup)")" = removed ] && echo "Auto-start is off." || echo "Auto-start was already off." ;;
      *) echo "Use: ./windows.sh autostart on|off" >&2; exit 2 ;;
    esac ;;
  -h|--help|"") usage ;;
  *) echo "Unknown command: $1" >&2; usage >&2; exit 2 ;;
esac
