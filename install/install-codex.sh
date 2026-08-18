#!/usr/bin/env bash
# Install the Codex/ChatGPT integration. Portable (macOS + Linux); points Codex
# at this checkout, so there's nothing to keep in sync. Idempotent.
#   bash install/install-codex.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"

# OS-correct interpreter token and repo path for the generated hook commands.
# Windows ships the interpreter as `python` (no `python3`) and needs a
# forward-slash path Codex/Git Bash can use; Unix uses `python3` and the native
# path. Mirrors merge-claude-settings.py.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) PCH_PY_TOK=python; ROOT_TOK="$(cygpath -m "$ROOT" 2>/dev/null || echo "$ROOT")" ;;
  *)                    PCH_PY_TOK=python3; ROOT_TOK="$ROOT" ;;
esac

command -v codex >/dev/null 2>&1 \
  && echo "-- detected the 'codex' CLI" \
  || echo "-- note: 'codex' CLI not on PATH; installing config anyway for when you add it"

mkdir -p "$CODEX_HOME"
# Back up an existing hooks.json before replacing it. Codex has no merge format
# for this file, so installing necessarily overwrites — but overwriting someone
# else's integration with no way back is not acceptable. This is not
# hypothetical: it clobbered a working unrelated Codex integration during
# testing, and without a backup the previous contents were unrecoverable.
if [ -f "$CODEX_HOME/hooks.json" ]; then
  if ! grep -q "$ROOT_TOK" "$CODEX_HOME/hooks.json" 2>/dev/null; then
    BACKUP="$CODEX_HOME/hooks.json.backup-$(date +%Y%m%d-%H%M%S)"
    cp "$CODEX_HOME/hooks.json" "$BACKUP"
    echo "!! $CODEX_HOME/hooks.json already exists and points somewhere else."
    echo "   Codex has no merge format for it, so it is being REPLACED."
    echo "   Backup: $BACKUP"
  fi
fi

sed -e "s#PCH_DIR#$ROOT_TOK#g" -e "s#PCH_PY#$PCH_PY_TOK#g" \
  "$ROOT/agents/codex/hooks.json.example" > "$CODEX_HOME/hooks.json"
echo "Installed Codex hooks -> $CODEX_HOME/hooks.json (pointing at $ROOT_TOK)"

mkdir -p "$AGENTS_HOME/skills/context-kb/agents"
cp "$ROOT/agents/shared-skill/context-kb/SKILL.md" "$AGENTS_HOME/skills/context-kb/SKILL.md"
cp "$ROOT/agents/shared-skill/context-kb/agents/openai.yaml" "$AGENTS_HOME/skills/context-kb/agents/openai.yaml"
echo "Installed shared skill -> $AGENTS_HOME/skills/context-kb"

echo "Restart Codex, then review and trust the hooks with /hooks if prompted."
