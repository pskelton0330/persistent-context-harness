#!/usr/bin/env bash
# Shared helpers for the harness CLIs. Source this; don't run it.
# Resolves the repo root, loads config, and derives KB_ROOT — all without any
# hardcoded user path.

# Resolve this file's real directory, following symlinks (mac + linux).
_pch_resolve_dir() {
  local src="$1" d
  while [ -h "$src" ]; do
    d="$(cd -P "$(dirname "$src")" && pwd)"; src="$(readlink "$src")"
    [[ $src != /* ]] && src="$d/$src"
  done
  cd -P "$(dirname "$src")" && pwd
}

PCH_BIN_DIR="$(_pch_resolve_dir "${BASH_SOURCE[0]}")"
PCH_ROOT="$(cd "$PCH_BIN_DIR/.." && pwd)"

# Load optional config (gitignored). Defaults keep everything working with none.
[ -f "$PCH_ROOT/config/harness.env" ] && . "$PCH_ROOT/config/harness.env"

KB_ROOT="${KB_ROOT:-$PCH_ROOT/wiki}"
KB_WORK_ROOTS="${KB_WORK_ROOTS:-$HOME}"
KB_RETRIEVER="${KB_RETRIEVER:-keyword}"
KB_SECRET_BACKEND="${KB_SECRET_BACKEND:-auto}"
KB_SECRET_SERVICE="${KB_SECRET_SERVICE:-context-harness}"

pch_die() { echo "error: $*" >&2; exit 1; }

# Is $1 inside any configured work root?
pch_in_work_scope() {
  local p; p="$(cd "$1" 2>/dev/null && pwd)" || return 1
  local IFS=:; local root
  for root in $KB_WORK_ROOTS; do
    [ -n "$root" ] || continue
    case "$p/" in "$root"/*|"$root"/) return 0 ;; esac
  done
  return 1
}
