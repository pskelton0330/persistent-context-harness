#!/usr/bin/env bash
# Schedule the weekly review: launchd on macOS, cron on Linux.
#   bash weekly/install-schedule.sh          # install (Sundays 10:00 local)
#   bash weekly/install-schedule.sh --remove
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RUNNER="$HERE/run-weekly.sh"
LABEL="com.context-harness.weekly"

remove=0
[ "${1:-}" = "--remove" ] && remove=1

if [ "$(uname -s)" = "Darwin" ]; then
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  if [ "$remove" = "1" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"; echo "removed $PLIST"; exit 0
  fi
  mkdir -p "$(dirname "$PLIST")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$RUNNER</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/state/weekly/launchd.log</string>
  <key>StandardErrorPath</key><string>$ROOT/state/weekly/launchd.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
</dict></plist>
EOF
  mkdir -p "$ROOT/state/weekly"
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "installed $PLIST (Sundays 10:00)"
  echo "run now:  launchctl start $LABEL"
else
  LINE="0 10 * * 0 /bin/bash $RUNNER >> $ROOT/state/weekly/cron.log 2>&1"
  current="$(crontab -l 2>/dev/null || true)"
  filtered="$(printf '%s\n' "$current" | grep -v 'run-weekly.sh' || true)"
  if [ "$remove" = "1" ]; then
    printf '%s\n' "$filtered" | crontab -; echo "removed weekly cron entry"; exit 0
  fi
  mkdir -p "$ROOT/state/weekly"
  printf '%s\n%s\n' "$filtered" "$LINE" | grep -v '^$' | crontab -
  echo "installed cron entry (Sundays 10:00):"; echo "  $LINE"
fi
