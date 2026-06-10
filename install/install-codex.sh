#!/usr/bin/env bash
# Install the Codex/ChatGPT integration. Portable (macOS + Linux); points Codex
# at this checkout, so there's nothing to keep in sync. Idempotent.
#   bash install/install-codex.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"

command -v codex >/dev/null 2>&1 \
  && echo "-- detected the 'codex' CLI" \
  || echo "-- note: 'codex' CLI not on PATH; installing config anyway for when you add it"

mkdir -p "$CODEX_HOME"
sed "s#PCH_DIR#$ROOT#g" "$ROOT/agents/codex/hooks.json.example" > "$CODEX_HOME/hooks.json"
echo "Installed Codex hooks -> $CODEX_HOME/hooks.json (pointing at $ROOT)"

mkdir -p "$AGENTS_HOME/skills/context-kb/agents"
cp "$ROOT/agents/shared-skill/context-kb/SKILL.md" "$AGENTS_HOME/skills/context-kb/SKILL.md"
cp "$ROOT/agents/shared-skill/context-kb/agents/openai.yaml" "$AGENTS_HOME/skills/context-kb/agents/openai.yaml"
echo "Installed shared skill -> $AGENTS_HOME/skills/context-kb"

echo "Restart Codex, then review and trust the hooks with /hooks if prompted."
