#!/usr/bin/env bash
# scan-secrets.sh — fail if staged (or given) files look like they contain a
# raw secret. Wire as a pre-commit hook:
#   ln -s ../../scripts/scan-secrets.sh .git/hooks/pre-commit
# Or scan the whole tree: scripts/scan-secrets.sh --all
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Read the file list into an array (Bash 3.2-safe — no mapfile).
files=()
while IFS= read -r line; do [ -n "$line" ] && files+=("$line"); done < <(
  if [ "${1:-}" = "--all" ]; then
    git -C "$ROOT" ls-files
  else
    git -C "$ROOT" diff --cached --name-only --diff-filter=ACM
  fi
)
[ "${#files[@]}" -gt 0 ] || { echo "scan-secrets: nothing to scan"; exit 0; }

# Patterns for raw secret VALUES. The scanner itself ships no secrets.
patterns='-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|(password|passwd|secret|token|api[_-]?key)[[:space:]]*[:=][[:space:]]*[A-Za-z0-9/+_-]{12,}|://[^/[:space:]:@]+:[^/[:space:]:@]+@'

hits=0
for f in "${files[@]}"; do
  [ -f "$ROOT/$f" ] || continue
  # Skip this scanner, the guard, and docs that describe the patterns.
  case "$f" in scripts/scan-secrets.sh|bin/credential-guard|docs/security.md) continue ;; esac
  if grep -nEI "$patterns" "$ROOT/$f" >/dev/null 2>&1; then
    echo "POSSIBLE SECRET in $f:"; grep -nEI "$patterns" "$ROOT/$f" | sed 's/^/  /'
    hits=$((hits+1))
  fi
done

if [ "$hits" -gt 0 ]; then
  echo; echo "scan-secrets: $hits file(s) flagged. Move values to the keychain (secret put) and retry."
  exit 1
fi
echo "scan-secrets: clean (${#files[@]} file(s))"
