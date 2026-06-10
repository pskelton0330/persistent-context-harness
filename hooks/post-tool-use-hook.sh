#!/usr/bin/env bash
# PostToolUse hook — record that this session edited files, so the Stop hook can
# give an edit-aware lesson-capture nudge. Optional: if you don't wire it, the
# Stop nudge still fires (just generically). Reads the hook JSON on stdin.
set -euo pipefail
payload="$(cat || true)"
sid="$(printf '%s' "$payload" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
mkdir -p "${TMPDIR:-/tmp}/pch-edits" 2>/dev/null || true
: > "${TMPDIR:-/tmp}/pch-edits/${sid:-default}" 2>/dev/null || true
exit 0
