#!/usr/bin/env bash
# Schedule the weekly review: launchd on macOS, cron on Linux, Task Scheduler
# (schtasks) on Windows/Git Bash.
#   bash weekly/install-schedule.sh          # install (Sundays 10:00 local)
#   bash weekly/install-schedule.sh --remove
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RUNNER="$HERE/run-weekly.sh"
LABEL="com.context-harness.weekly"
# A stable marker used to identify OUR entry precisely — so removal never touches
# an unrelated job that merely mentions run-weekly.sh, and re-install replaces
# rather than duplicates.
MARKER="# $LABEL"

remove=0
[ "${1:-}" = "--remove" ] && remove=1

case "$(uname -s 2>/dev/null)" in
  Darwin) OS=mac ;;
  MINGW*|MSYS*|CYGWIN*) OS=windows ;;
  *) OS=linux ;;
esac

# Minimal XML entity-escaping for values interpolated into the launchd plist.
# Without it a '&', '<' or '>' anywhere in the repo path produces an invalid
# plist that launchctl silently refuses to load.
xml_escape() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

# POSIX single-quote serialization: wrap in single quotes, and render any
# embedded single quote as the '\'' idiom. The result is one safe shell word for
# ANY content (spaces, $, backticks, ", backslash, apostrophes), which is what
# the cron command needs since cron hands the line to `/bin/sh -c`.
shq() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# Drop empty PATH components (a leading/trailing ':' or a '::' means "current
# directory" — an unsafe search element for an unattended job).
sanitize_path() {
  printf '%s' "$1" | sed -E 's/:+/:/g; s/^://; s/:$//'
}

if [ "$OS" = mac ]; then
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  if [ "$remove" = "1" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"; echo "removed $PLIST"; exit 0
  fi
  mkdir -p "$(dirname "$PLIST")" "$ROOT/state/weekly"
  e_label="$(xml_escape "$LABEL")"
  e_runner="$(xml_escape "$RUNNER")"
  e_log="$(xml_escape "$ROOT/state/weekly/launchd.log")"
  # Give the scheduled job the SAME PATH the installing shell has (minus empty
  # components), so a user-local agent CLI (claude/codex) and python are found
  # on schedule exactly as interactively — the previous hard-coded PATH missed
  # them.
  e_path="$(xml_escape "$(sanitize_path "$PATH")")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$e_label</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$e_runner</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$e_log</string>
  <key>StandardErrorPath</key><string>$e_log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$e_path</string></dict>
</dict></plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "installed $PLIST (Sundays 10:00)"
  echo "run now:  launchctl start $LABEL"

elif [ "$OS" = windows ]; then
  # Windows Task Scheduler via schtasks. The action launches Git Bash to run the
  # runner; paths are converted to Windows form. schtasks has no merge, so we
  # delete any prior task of the same name first (idempotent).
  TASK="ContextHarnessWeekly"
  BASH_EXE=""
  for c in "/c/Program Files/Git/bin/bash.exe" "/c/Program Files (x86)/Git/bin/bash.exe"; do
    [ -x "$c" ] && { BASH_EXE="$c"; break; }
  done
  [ -n "$BASH_EXE" ] || BASH_EXE="$(command -v bash)"
  if [ "$remove" = "1" ]; then
    schtasks //Delete //TN "$TASK" //F >/dev/null 2>&1 || true
    echo "removed scheduled task $TASK"; exit 0
  fi
  mkdir -p "$ROOT/state/weekly"
  win_bash="$(cygpath -w "$BASH_EXE")"
  runner_posix="$(cygpath -m "$RUNNER")"
  # The action nests three parsers (Task Scheduler → cmd → bash -lc → bash), and
  # a quote character in either path cannot be carried through them safely. Refuse
  # rather than store a task that would misparse at run time; point the user at a
  # manual setup with the exact command.
  case "$win_bash$runner_posix" in
    *\'*|*\"*)
      echo "!! the Git-Bash or checkout path contains a quote character;" >&2
      echo "   refusing to build a Task Scheduler action that would misparse it." >&2
      echo "   Create a weekly task manually that runs:  bash \"$runner_posix\"" >&2
      exit 1 ;;
  esac
  # //-form flags so MSYS does not mangle the leading slash. The action string
  # is what Task Scheduler stores; inner quoting is for cmd's parser.
  action="\"$win_bash\" -lc \"bash '$runner_posix'\""
  schtasks //Delete //TN "$TASK" //F >/dev/null 2>&1 || true
  if schtasks //Create //TN "$TASK" //TR "$action" //SC WEEKLY //D SUN //ST 10:00 //F >/dev/null 2>&1; then
    echo "installed scheduled task '$TASK' (Sundays 10:00)"
    echo "run now:  schtasks //Run //TN $TASK"
  else
    echo "!! could not create the scheduled task automatically." >&2
    echo "   Create one in Task Scheduler that runs, weekly:" >&2
    echo "     $action" >&2
    exit 1
  fi

else
  # Linux / other: cron. Identify our entry by the trailing MARKER so removal is
  # exact. Serialize every interpolated value with shq() so any character in the
  # checkout path survives the `/bin/sh -c` cron runs. Inject the installing
  # shell's PATH (empty components stripped) so the agent CLI is found.
  LOGF="$ROOT/state/weekly/cron.log"
  SAFE_PATH="$(sanitize_path "$PATH")"
  # A crontab is line-oriented: a CR or LF in any interpolated value would add or
  # corrupt records (shq cannot serialize a newline through this format). Refuse,
  # fail-closed, rather than mutate the user's crontab.
  case "$SAFE_PATH$RUNNER$LOGF" in
    *$'\n'*|*$'\r'*)
      echo "!! a scheduled path or the PATH contains a newline; refusing to write" >&2
      echo "   a crontab entry. Fix the path/PATH, or add the schedule manually." >&2
      exit 1 ;;
  esac
  CMD="PATH=$(shq "$SAFE_PATH") /bin/bash $(shq "$RUNNER") >> $(shq "$LOGF") 2>&1"
  # cron interprets an unescaped '%' in the command as a newline BEFORE the shell
  # sees it, so escape every '%' to '\%'. cron strips the backslash and passes a
  # literal '%' to the shell.
  CMD="$(printf '%s' "$CMD" | sed 's/%/\\%/g')"
  LINE="0 10 * * 0 $CMD $MARKER"
  current="$(crontab -l 2>/dev/null || true)"
  # Drop only OUR marked line(s); -F so the marker is a literal, not a regex.
  filtered="$(printf '%s\n' "$current" | grep -vF "$MARKER" || true)"
  if [ "$remove" = "1" ]; then
    printf '%s\n' "$filtered" | grep -v '^$' | crontab - 2>/dev/null || printf '' | crontab -
    echo "removed weekly cron entry"; exit 0
  fi
  mkdir -p "$ROOT/state/weekly"
  printf '%s\n%s\n' "$filtered" "$LINE" | grep -v '^$' | crontab -
  echo "installed cron entry (Sundays 10:00):"; echo "  $LINE"
fi
