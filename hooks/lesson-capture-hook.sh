#!/usr/bin/env bash
# Stop hook — after a turn that edited files, nudge the agent to capture a
# durable lesson if the work was non-trivial. Prints a reminder to stdout.
# Keep it advisory: the agent decides whether a lesson is warranted.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HOOK_DIR/.." && pwd)"
. "$ROOT/bin/_common.sh"

# Once per session: a stamp file keyed by the host-provided session id (if any).
payload="$(cat || true)"
sid="$(printf '%s' "$payload" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
stamp="${TMPDIR:-/tmp}/pch-lesson-nudge-${sid:-default}"
[ -e "$stamp" ] && exit 0
: > "$stamp"

# If the PostToolUse hook recorded edits this session, give an edit-aware nudge.
if [ -e "${TMPDIR:-/tmp}/pch-edits/${sid:-default}" ]; then
  echo "This session edited files. If the fix was non-trivial, hit a surprising root"
  echo "cause, or made a non-obvious decision, capture it: kb lesson \"<short title>\"."
else
  echo "If this session fixed a non-trivial bug, hit a surprising root cause, or made"
  echo "a non-obvious decision, capture it: kb lesson \"<short title>\" (then fill it in)."
fi
