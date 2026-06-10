#!/usr/bin/env bash
# Wire the harness into Claude Code. Independent of the other agents.
# Generates a settings snippet with absolute paths filled in and (optionally)
# installs the project guidelines. Idempotent.
#   bash install/install-claude.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

command -v claude >/dev/null 2>&1 \
  && echo "-- detected the 'claude' CLI" \
  || echo "-- note: 'claude' CLI not on PATH; installing config anyway for when you add it"

gen="$ROOT/config/claude-settings.generated.json"
sed "s#PCH_DIR#$ROOT#g" "$ROOT/agents/claude/settings.json.example" > "$gen"
echo "-- wrote $gen"
echo "   Merge its \"hooks\" block into ~/.claude/settings.json (or a project .claude/settings.json)."
echo "   Project guidelines template: $ROOT/agents/claude/CLAUDE.md"
echo "   Slash commands: copy $ROOT/agents/claude/commands/* into your .claude/commands/ if you want them."
echo "Done. Claude Code will prime context on session start once the hooks are merged."
