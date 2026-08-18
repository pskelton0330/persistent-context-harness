#!/usr/bin/env bash
# Wire the harness into Claude Code. Independent of the other agents.
# Safely MERGES the harness hooks into ~/.claude/settings.json (preserving every
# other setting, keeping hooks that belong to anything else, writing a backup),
# with OS-correct interpreter and paths. Idempotent.
#   bash install/install-claude.sh              # merge (shows a dry-run first)
#   bash install/install-claude.sh --uninstall  # remove exactly our entries
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
. "$ROOT/bin/_common.sh"   # for PCH_PYTHON (python3 on Unix, python on Windows)

command -v claude >/dev/null 2>&1 \
  && echo "-- detected the 'claude' CLI" \
  || echo "-- note: 'claude' CLI not on PATH; installing config anyway for when you add it"

MERGE="$ROOT/install/merge-claude-settings.py"

case "${1:-}" in
  --uninstall)
    shift
    "$PCH_PYTHON" "$MERGE" --uninstall "$@"
    ;;
  *)
    # Show what will change, then apply. The merge script writes a timestamped
    # backup and only ever touches the "hooks" key.
    echo "-- planned change to your Claude settings.json:"
    "$PCH_PYTHON" "$MERGE" --dry-run "$@"
    "$PCH_PYTHON" "$MERGE" "$@"
    echo "   Project guidelines template: $ROOT/agents/claude/CLAUDE.md"
    echo "   Slash commands: copy $ROOT/agents/claude/commands/* into your .claude/commands/ if you want them."
    echo "Done. Restart Claude Code so the hooks load; it will prime context on session start."
    ;;
esac
