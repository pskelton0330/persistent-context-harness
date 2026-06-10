#!/usr/bin/env bash
# SessionStart hook — prime hot context when a session opens inside a work root.
# Wired into Claude Code (settings.json) and Codex (via the python shim). Reads
# the hook JSON payload on stdin; prints context to stdout for the host to inject.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HOOK_DIR/.." && pwd)"
. "$ROOT/bin/_common.sh"

payload="$(cat || true)"
cwd="$(printf '%s' "$payload" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
cwd="${cwd:-$PWD}"

# Only prime inside configured work roots; stay silent elsewhere.
pch_in_work_scope "$cwd" || exit 0
"$ROOT/bin/kb" context "$cwd"
