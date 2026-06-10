#!/usr/bin/env bash
# UserPromptSubmit hook — when the user reports a problem, surface matching
# lessons BEFORE the agent starts debugging. Reads the hook JSON on stdin;
# prints matching lessons to stdout for the host to inject as context.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HOOK_DIR/.." && pwd)"
. "$ROOT/bin/_common.sh"

payload="$(cat || true)"
prompt="$(printf '%s' "$payload" | sed -n 's/.*"prompt"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
[ -n "$prompt" ] || exit 0

# Only fire on problem-shaped prompts to avoid noise.
echo "$prompt" | grep -qiE "doesn'?t work|not working|broken|error|fail|stuck|slow|stopped|why (is|does|are)|times? out|crash" || exit 0

matches="$("$ROOT/bin/kb" recall "$prompt" 2>/dev/null | grep -v '^(no matching' || true)"
[ -n "$matches" ] || exit 0
echo "Relevant past lessons (read before debugging):"
echo "$matches"
