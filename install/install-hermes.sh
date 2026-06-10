#!/usr/bin/env bash
# Wire the harness into Hermes (optional/external). Independent of the other
# agents. Installs the shared context-kb skill so `hermes --skills context-kb`
# (and bin/hermes-context) work. Idempotent.
#   bash install/install-hermes.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"

command -v hermes >/dev/null 2>&1 \
  && echo "-- detected the 'hermes' CLI" \
  || echo "-- note: 'hermes' is a separate tool and isn't on PATH. This integration is"
echo "         optional; Claude Code and Codex work fine without it."

mkdir -p "$AGENTS_HOME/skills/context-kb/agents"
cp "$ROOT/agents/shared-skill/context-kb/SKILL.md" "$AGENTS_HOME/skills/context-kb/SKILL.md"
cp "$ROOT/agents/shared-skill/context-kb/agents/openai.yaml" "$AGENTS_HOME/skills/context-kb/agents/openai.yaml"
echo "-- installed shared skill -> $AGENTS_HOME/skills/context-kb"
echo "Launch with: $ROOT/bin/hermes-context   (= hermes --skills context-kb)"
