#!/usr/bin/env bash
# Shared helpers for the harness CLIs. Source this; don't run it.
# Resolves the repo root, loads config, and derives KB_ROOT — all without any
# hardcoded user path. POSIX-compatible: also sourceable from sh/dash/zsh.

# Resolve this file's real directory, following symlinks (mac + linux).
# Uses POSIX `case` rather than bash `[[ ]]` so this works under dash/sh, where
# `[[` is not a builtin and the relative-symlink branch would otherwise fail.
_pch_resolve_dir() {
  _src="$1"
  while [ -h "$_src" ]; do
    _d="$(cd -P "$(dirname "$_src")" && pwd)"
    _src="$(readlink "$_src")"
    case "$_src" in
      /*) ;;                 # already absolute
      *) _src="$_d/$_src" ;; # rebase relative link onto the link's directory
    esac
  done
  cd -P "$(dirname "$_src")" && pwd
}

# Find our own path. BASH_SOURCE is unset under zsh (the macOS default shell),
# so cover that case too -- the zsh form is eval'd because bash cannot parse it.
if [ -n "${BASH_SOURCE:-}" ]; then
  _pch_self="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  eval '_pch_self="${(%):-%x}"'
else
  _pch_self="$0"
fi

PCH_BIN_DIR="$(_pch_resolve_dir "$_pch_self")"
PCH_ROOT="$(cd "$PCH_BIN_DIR/.." 2>/dev/null && pwd)"

# Validate what we resolved. Strict POSIX shells (dash) provide no way for a
# SOURCED file to learn its own path -- $0 is the shell name -- so the guesses
# above can silently land on the wrong directory. Resolving to the wrong root is
# far worse than failing: it would load someone else's config and mis-scope
# every hook. Check, self-correct where unambiguous, else say so loudly.
if [ ! -f "$PCH_ROOT/bin/_common.sh" ]; then
  if [ -f "$PCH_BIN_DIR/bin/_common.sh" ]; then
    # We landed on the repo root rather than bin/.
    PCH_ROOT="$PCH_BIN_DIR"
    PCH_BIN_DIR="$PCH_ROOT/bin"
  elif [ -n "${PCH_ROOT_OVERRIDE:-}" ] && [ -f "$PCH_ROOT_OVERRIDE/bin/_common.sh" ]; then
    PCH_ROOT="$PCH_ROOT_OVERRIDE"
    PCH_BIN_DIR="$PCH_ROOT/bin"
  else
    echo "context-harness: cannot locate the harness root from this shell" \
         "(resolved '$PCH_ROOT', which has no bin/_common.sh). Your shell does" \
         "not support locating a sourced file; re-run under bash or zsh, or" \
         "export PCH_ROOT_OVERRIDE=/path/to/persistent-context-harness." >&2
    return 1 2>/dev/null || exit 1
  fi
fi
unset _pch_self _src _d

# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------
# One place decides OS-specific behaviour. Git Bash / MSYS / Cygwin report an
# MINGW*/MSYS*/CYGWIN* uname, which is how a Windows box running the shell CLIs
# is recognized. Everything downstream keys off PCH_OS rather than re-running
# uname, so the rules can never drift between call sites.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) PCH_OS=windows ;;
  Darwin)               PCH_OS=mac ;;
  Linux)                PCH_OS=linux ;;
  *)                    PCH_OS=other ;;
esac

# Separator for KB_WORK_ROOTS / KB_EXCLUDED_ROOTS. It is os.pathsep: ';' on
# Windows, ':' elsewhere. A Unix ':' would split a Windows path on its drive
# letter ("C:\Users" -> "C", "\Users"), which silently breaks project scope.
if [ "$PCH_OS" = windows ]; then PCH_PATHSEP=";"; else PCH_PATHSEP=":"; fi

# The plain interpreter for stdlib scripts. Windows ships it as `python`, not
# `python3`; Unix as `python3`. Callers that honour KB_PYTHON (the venv with the
# semantic extras) apply that override themselves — this is only the fallback.
if command -v python3 >/dev/null 2>&1; then PCH_PYTHON=python3
elif command -v python >/dev/null 2>&1; then PCH_PYTHON=python
else PCH_PYTHON=python3; fi

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# The config file is READ, never sourced. Sourcing let shell and Python diverge
# on quoting, escapes and expansion, so one syntactically valid file could yield
# different roots in a shell hook than in a Python hook. Both now implement the
# same strict grammar (see lib/harness_config.py for the full statement):
#
#   KEY=VALUE, whole-line '#' comments, optional surrounding quotes, values are
#   LITERAL except a leading ~/ $HOME/ ${HOME}/ which expands.
#
# Only KEY=VALUE lines whose KEY is not already set in the environment are
# applied, so the environment keeps winning over the file.

# Keys the harness understands. Only these are read from the file; an unknown
# key cannot inject a variable into the shell.
# Written across several lines for readability, then normalized to single
# spaces: the membership test below matches on " $key ", so a key sitting at a
# line end would otherwise never match and would silently fall back to its
# default. (That bug shipped briefly and the parity test caught it.)
PCH_KEYS="KB_ROOT KB_WORK_ROOTS KB_EXCLUDED_ROOTS KB_STATE_DIR KB_RETRIEVER
KB_EMBED_URL KB_EMBED_MODEL KB_EMBED_DIM KB_PYTHON KB_WEEKLY_AGENT
KB_SECRET_BACKEND KB_SECRET_SERVICE"
PCH_KEYS="$(printf '%s' "$PCH_KEYS" | tr '\n\t' '  ')"

# Record which keys were already set in the ENVIRONMENT, before any file line is
# applied. Without this snapshot, the first assignment in the file makes the
# "already set?" test true for later duplicates, so shell would keep the FIRST
# duplicate while Python keeps the LAST -- a silent split-brain.
# Split a delimited string into lines. zsh does NOT word-split unquoted
# parameter expansions, so the idiomatic `for x in $VAR` iterates exactly once
# there with the whole string as one word -- silently breaking every loop that
# relies on splitting. Feeding a here-document into `while read` splits
# correctly in every shell AND keeps the loop in the current shell, so
# assignments inside it survive (a pipeline would not).
_pch_split() { printf '%s' "$1" | tr "$2" '\n'; }

# Indirection is written as `eval "_v=\$NAME"` rather than `${$NAME:-}`: zsh
# rejects the latter with "bad substitution".
_pch_preset=" "
while IFS= read -r _k; do
  [ -n "$_k" ] || continue
  # `:-` is required: callers run with `set -u`, where expanding an unset
  # variable is a fatal error. The zsh problem was the ${$name} indirection
  # form, not the default -- after expansion this is a plain ${KB_ROOT:-}.
  eval "_pch_v=\${$_k:-}" 2>/dev/null || _pch_v=""
  # `if`, not `[ ] && ...`: an AND-list whose test fails returns non-zero, and
  # as the last statement in a loop or function that aborts any caller running
  # under `set -e` (which every bin/ script does).
  if [ -n "${_pch_v:-}" ]; then
    _pch_preset="$_pch_preset$_k "
  fi
done <<EOF
$(_pch_split "$PCH_KEYS" ' ')
EOF
unset _k _pch_v

# Trim leading/trailing spaces and tabs, matching Python's str.strip() for the
# whitespace this grammar allows.
_pch_trim() {
  _t="$1"
  while :; do
    case "$_t" in
      " "*) _t=${_t# } ;;
      "$(printf '\t')"*) _t=${_t#"$(printf '\t')"} ;;
      *) break ;;
    esac
  done
  while :; do
    case "$_t" in
      *" ") _t=${_t% } ;;
      *"$(printf '\t')") _t=${_t%"$(printf '\t')"} ;;
      *) break ;;
    esac
  done
  printf '%s' "$_t"
}

_pch_load_config() {
  _cfg="$PCH_ROOT/config/harness.env"
  [ -f "$_cfg" ] || return 0
  # Mirror MAX_CONFIG_BYTES in lib/harness_config.py: both implementations must
  # reject the same oversized file, or they would resolve different settings.
  _size=$(wc -c < "$_cfg" 2>/dev/null || echo 0)
  if [ "${_size:-0}" -gt 65536 ]; then
    echo "context-harness: config: $_cfg exceeds 65536 bytes; ignored" >&2
    unset _cfg _size
    return 0
  fi
  unset _size
  while IFS= read -r _line || [ -n "$_line" ]; do
    # Normalize CRLF; otherwise a file authored on Windows leaves a trailing
    # \r in shell values that Python's splitlines() strips.
    _line=${_line%"$(printf '\r')"}

    _line=$(_pch_trim "$_line")
    case "$_line" in
      ''|'#'*) continue ;;
      *=*) ;;
      *) _pch_cfg_warn "not KEY=VALUE"; continue ;;
    esac

    _key=${_line%%=*}
    _val=${_line#*=}

    # Accept a leading `export ` exactly as the Python parser does.
    case "$_key" in
      export\ *|export"$(printf '\t')"*) _key=${_key#export} ;;
    esac
    # Leading whitespace only. Trailing whitespace is NOT trimmed, so
    # `KEY =value` stays invalid — Python's regex requires the key to end
    # immediately before `=`, and bash sourcing would reject it too.
    while :; do
      case "$_key" in
        " "*) _key=${_key# } ;;
        "$(printf '\t')"*) _key=${_key#"$(printf '\t')"} ;;
        *) break ;;
      esac
    done

    # Must be an identifier: leading letter or underscore. Python's regex
    # rejects digit-leading keys, so this must too.
    case "$_key" in
      ''|[!A-Za-z_]*|*[!A-Za-z0-9_]*) _pch_cfg_warn "bad key '$_key'"; continue ;;
    esac
    # Ignore keys the harness does not define.
    case "$_pch_preset$PCH_KEYS " in
      *" $_key "*) ;;
      *) continue ;;
    esac

    _val=$(_pch_trim "$_val")
    case "$_val" in
      \"*)
        _rest=${_val#\"}
        case "$_rest" in
          *\"*) _tail=${_rest#*\"}; _val=${_rest%%\"*} ;;
          *) _pch_cfg_warn "unterminated quote for $_key"; continue ;;
        esac
        _tail=$(_pch_trim "$_tail")
        case "$_tail" in
          ''|'#'*) ;;
          *) _pch_cfg_warn "trailing text after quoted $_key"; continue ;;
        esac
        ;;
      \'*)
        _rest=${_val#\'}
        case "$_rest" in
          *\'*) _tail=${_rest#*\'}; _val=${_rest%%\'*} ;;
          *) _pch_cfg_warn "unterminated quote for $_key"; continue ;;
        esac
        _tail=$(_pch_trim "$_tail")
        case "$_tail" in
          ''|'#'*) ;;
          *) _pch_cfg_warn "trailing text after quoted $_key"; continue ;;
        esac
        ;;
      *) _val=$(_pch_trim "${_val%% #*}") ;;
    esac

    # Same diagnostics the Python parser emits: the file is never sourced, so
    # these are literal here even though a shell reader would expect expansion.
    case "$_val" in
      *'$('*|*'`'*) _pch_cfg_note "$_key contains command substitution; used literally" ;;
      '~/'*|'$HOME/'*|'${HOME}/'*|'~'|'$HOME'|'${HOME}') ;;
      *'$'*) _pch_cfg_note "$_key contains '\$'; only a leading \$HOME is expanded" ;;
    esac

    # Expand only a leading home reference, matching the Python parser exactly.
    case "$_val" in
      '~/'*) _val="$HOME/${_val#\~/}" ;;
      '$HOME/'*) _val="$HOME/${_val#\$HOME/}" ;;
      '${HOME}/'*) _val="$HOME/${_val#\$\{HOME\}/}" ;;
      '~'|'$HOME'|'${HOME}') _val="$HOME" ;;
    esac

    [ -n "$_val" ] || continue
    # Environment (as captured BEFORE parsing) wins over the file.
    case "$_pch_preset" in *" $_key "*) continue ;; esac
    # Last duplicate wins, matching the Python dict-assignment behaviour.
    eval "$_key=\$_val"
  done < "$_cfg"
  unset _cfg _line _key _val _rest _tail _t
  return 0
}

# Config warnings go to stderr, at most a few, so a malformed file is visible
# rather than silently half-applied.
_pch_cfg_warned=0
_pch_cfg_warn() {
  if [ "$_pch_cfg_warned" -lt 5 ]; then
    _pch_cfg_warned=$((_pch_cfg_warned + 1))
    echo "context-harness: config: $*; line ignored" >&2
  fi
  return 0
}

# A note is for a value that IS applied but may not behave as a shell user
# expects; a warn is for a line that is discarded.
_pch_cfg_note() {
  if [ "$_pch_cfg_warned" -lt 5 ]; then
    _pch_cfg_warned=$((_pch_cfg_warned + 1))
    echo "context-harness: config: $*" >&2
  fi
  return 0
}

_pch_load_config

KB_ROOT="${KB_ROOT:-$PCH_ROOT/wiki}"
KB_WORK_ROOTS="${KB_WORK_ROOTS:-$HOME}"
# Lowercased to match lib/harness_config.py, so "Semantic" and "SEMANTIC" select
# the same retriever in shell and Python components.
KB_RETRIEVER="$(printf '%s' "${KB_RETRIEVER:-keyword}" | tr 'A-Z' 'a-z')"
KB_SECRET_BACKEND="${KB_SECRET_BACKEND:-auto}"
KB_SECRET_SERVICE="${KB_SECRET_SERVICE:-context-harness}"
KB_EXCLUDED_ROOTS="${KB_EXCLUDED_ROOTS:-}"

# Generated artifacts (vector index, retrieval log, weekly drafts + run logs).
# Deliberately outside KB_ROOT: this is machine state, not knowledge, and must
# never land in the user's KB git history.
KB_STATE_DIR="${KB_STATE_DIR:-$PCH_ROOT/state}"

# Interpreter for the semantic index and weekly pipeline (needs third-party
# packages, so the installer points it at a venv). Empty = those extras are not
# installed; plain hooks stay stdlib-only and run under any python3.
KB_PYTHON="${KB_PYTHON:-}"

# Embedding backend for semantic recall.
KB_EMBED_URL="${KB_EMBED_URL:-http://localhost:11434/api/embed}"
KB_EMBED_MODEL="${KB_EMBED_MODEL:-nomic-embed-text}"
# Validated and range-checked exactly as lib/harness_config.py does, so a bad
# value cannot leave shell and Python components using different dimensions.
KB_EMBED_DIM="${KB_EMBED_DIM:-768}"
case "$KB_EMBED_DIM" in
  ''|*[!0-9]*) KB_EMBED_DIM=768 ;;
  *) [ "$KB_EMBED_DIM" -ge 1 ] 2>/dev/null && [ "$KB_EMBED_DIM" -le 65536 ] 2>/dev/null || KB_EMBED_DIM=768 ;;
esac

# Agent CLI used for the weekly reasoning passes, in place of a pinned local
# model. Must accept a prompt on stdin in headless mode.
KB_WEEKLY_AGENT="${KB_WEEKLY_AGENT:-claude}"

# Mirror of lib/harness_config.py. Keep the two in step -- a shell hook and a
# Python hook must never disagree about where the KB is.
PCH_PY="$PCH_ROOT/lib/harness_config.py"

pch_die() { echo "error: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Scope predicates
# ---------------------------------------------------------------------------
# These delegate to lib/harness_config.py so there is exactly ONE implementation
# of scope logic. The pure-shell loop is only a fallback for when python3 is
# unavailable; it cannot see project-roots.json and compares paths by spelling.

# True when the authoritative Python resolver is usable.
_pch_have_py() { command -v python3 >/dev/null 2>&1 && [ -f "$PCH_PY" ]; }

# Warn once per process when we degrade to the shell fallback. Silent
# degradation is how a broken component hides for weeks; say so out loud.
_pch_warned_fallback=""
_pch_warn_fallback() {
  if [ -n "$_pch_warned_fallback" ]; then
    return 0
  fi
  _pch_warned_fallback=1
  echo "context-harness: warning — lib/harness_config.py unavailable at" \
       "'$PCH_PY'; using reduced shell scope rules (project-roots.json and" \
       "case/symlink-aware matching are unavailable). Run bin/kb-selftest." >&2
}

# Canonicalize a directory for comparison. Resolves symlinks via `cd -P` so the
# fallback compares physical paths on both sides -- comparing a physical
# candidate against an unresolved symlink spelling would let retrieval fire
# inside the KB.
_pch_canon() { cd -P "$1" 2>/dev/null && pwd; }

# Is $1 inside any configured work root?
pch_in_work_scope() {
  if _pch_have_py; then
    python3 "$PCH_PY" --contains "$1" >/dev/null 2>&1
    return $?
  fi
  _pch_warn_fallback
  _p="$(_pch_canon "$1")" || return 1
  [ -n "$_p" ] || return 1
  _hit=1
  while IFS= read -r _root; do
    [ -n "$_root" ] || continue
    _r="$(_pch_canon "$_root")" || _r="$_root"
    case "$_p/" in "$_r"/*|"$_r"/) _hit=0 ;; esac
  done <<EOF
$(_pch_split "$KB_WORK_ROOTS" "$PCH_PATHSEP")
EOF
  unset _p _r _root
  return $_hit
}

# The gate hooks should actually use: in a managed project AND not inside the
# KB itself. Retrieving KB context into a session that is editing the KB
# creates a feedback loop and fills the retrieval log with vault maintenance.
pch_should_retrieve() {
  if _pch_have_py; then
    python3 "$PCH_PY" --retrieve "$1" >/dev/null 2>&1
    return $?
  fi
  pch_in_work_scope "$1" || return 1
  # Canonicalize BOTH sides before comparing, and honour configured exclusions.
  _p="$(_pch_canon "$1")" || return 1
  _kb="$(_pch_canon "$KB_ROOT")" || _kb="$KB_ROOT"
  case "$_p/" in "$_kb"/*|"$_kb"/) unset _p _kb; return 1 ;; esac
  _excluded=0
  while IFS= read -r _root; do
    [ -n "$_root" ] || continue
    _r="$(_pch_canon "$_root")" || _r="$_root"
    case "$_p/" in "$_r"/*|"$_r"/) _excluded=1 ;; esac
  done <<EOF
$(_pch_split "${KB_EXCLUDED_ROOTS:-}" "$PCH_PATHSEP")
EOF
  unset _p _kb _r _root
  [ "$_excluded" -eq 0 ]
}
