#!/usr/bin/env bash
# Differential test: bin/_common.sh and lib/harness_config.py must interpret
# config/harness.env IDENTICALLY.
#
# These are two hand-written parsers of the same grammar, so they can drift.
# When they do, a shell CLI and a Python hook silently disagree about where the
# KB is or which directories are in scope — the worst kind of bug this project
# can have, because nothing errors.
#
# Runs every fixture through both implementations, under each available shell.
#
#   bash tests/test_parser_parity.sh
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# On Windows, keep the workspace in a form native Python and Git Bash both
# resolve identically (see the note in test_hooks.sh). No-op off MSYS/Cygwin.
if command -v cygpath >/dev/null 2>&1; then WORK="$(cygpath -m "$WORK")"; fi

# A throwaway harness root. bin/_common.sh locates itself by real path, so the
# files must be copied rather than symlinked for PCH_ROOT to land here.
HARNESS="$WORK/harness"
mkdir -p "$HARNESS/config"
cp -R "$REPO/bin" "$HARNESS/bin"
cp -R "$REPO/lib" "$HARNESS/lib"

PASS=0
FAIL=0
# python3 on Unix, python on Windows (Git Bash has no python3).
if command -v python3 >/dev/null 2>&1; then PYBIN=python3
elif command -v python >/dev/null 2>&1; then PYBIN=python
else echo "no python interpreter found" >&2; exit 1; fi
SHELLS=""
for candidate in bash zsh sh dash ksh; do
  command -v "$candidate" >/dev/null 2>&1 && SHELLS="$SHELLS $candidate"
done
# On Windows (MSYS/MINGW/Cygwin) the harness only ever runs under bash — Git Bash
# is what Claude Code and the CLIs use. MSYS also ships a minimal `dash` that
# cannot self-locate a sourced file (no BASH_SOURCE, and its `$0` under `-c`
# differs), which the harness never relies on there. Testing it would report a
# failure for a shell that is never used on the platform, so scope parity to bash
# on Windows. Unix keeps testing every available POSIX shell.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) SHELLS=" bash" ;;
esac

# Read one variable the way the SHELL implementation does.
shell_value() {
  local shell="$1" key="$2"
  "$shell" -c '
    cd "$1" || exit 1
    . "$1/bin/_common.sh" 2>/dev/null
    eval "printf %s \"\${$2-<unset>}\""
  ' _ "$HARNESS" "$key" 2>/dev/null
}

# Read the same variable the way the PYTHON implementation does.
python_value() {
  local key="$1"
  "$PYBIN" - "$HARNESS" "$key" <<'PY' 2>/dev/null
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "lib"))
from harness_config import HarnessConfig
cfg = HarnessConfig(root=root)
attr = {
    "KB_ROOT": lambda c: str(c.kb_root),
    "KB_STATE_DIR": lambda c: str(c.state_dir),
    "KB_WORK_ROOTS": lambda c: ":".join(str(p) for p in c.project_roots),
    "KB_EMBED_MODEL": lambda c: c.embed_model,
    "KB_EMBED_URL": lambda c: c.embed_url,
    "KB_EMBED_DIM": lambda c: str(c.embed_dim),
    "KB_PYTHON": lambda c: c.python or "",
    "KB_WEEKLY_AGENT": lambda c: c.weekly_agent,
    "KB_RETRIEVER": lambda c: c.retriever,
    "KB_SECRET_BACKEND": lambda c: c.secret_backend,
    "KB_SECRET_SERVICE": lambda c: c.secret_service,
}[sys.argv[2]]
print(attr(cfg), end="")
PY
}

# Compare both implementations for one fixture.
#   check <description> <key> <config-body>
check() {
  local description="$1" key="$2" body="$3"
  printf '%b' "$body" > "$HARNESS/config/harness.env"

  local py
  py="$(python_value "$key")"

  # Python stores path settings as RESOLVED Paths (needed so scope comparison is
  # correct across symlinks and case-insensitive filesystems); shell keeps the
  # raw string. Those are the same directory, so path-valued keys are compared
  # after resolving both sides. Every other key is compared verbatim.
  local is_path=0
  case "$key" in KB_ROOT|KB_STATE_DIR|KB_WORK_ROOTS) is_path=1 ;; esac

  local shell result a b mismatch=""
  for shell in $SHELLS; do
    result="$(shell_value "$shell" "$key")"
    if [ "$is_path" -eq 1 ]; then
      a="$(cd "$(dirname "$result")" 2>/dev/null && printf '%s/%s' "$(pwd -P)" "$(basename "$result")")"
      b="$(cd "$(dirname "$py")" 2>/dev/null && printf '%s/%s' "$(pwd -P)" "$(basename "$py")")"
      [ -n "$a" ] && [ "$a" = "$b" ] || mismatch="$mismatch $shell='$result'"
    else
      [ "$result" = "$py" ] || mismatch="$mismatch $shell='$result'"
    fi
  done

  if [ -z "$mismatch" ]; then
    PASS=$((PASS + 1))
    printf '  ok    %-44s py=%s\n' "$description" "${py:0:28}"
  else
    FAIL=$((FAIL + 1))
    printf '  FAIL  %-44s py='"'"'%s'"'"' vs%s\n' "$description" "$py" "$mismatch"
  fi
}

echo "== config parser parity (shells:$SHELLS) =="

check "plain assignment"              KB_EMBED_MODEL 'KB_EMBED_MODEL=plain\n'
check "double-quoted value"           KB_EMBED_MODEL 'KB_EMBED_MODEL="quoted value"\n'
check "single-quoted value"           KB_EMBED_MODEL "KB_EMBED_MODEL='quoted value'\n"
check "export prefix"                 KB_EMBED_MODEL 'export KB_EMBED_MODEL=exported\n'
check "leading whitespace"            KB_EMBED_MODEL '   KB_EMBED_MODEL=indented\n'
check "space before ="                KB_EMBED_MODEL 'KB_EMBED_MODEL =spaced\n'
check "space after ="                 KB_EMBED_MODEL 'KB_EMBED_MODEL= spaced\n'
check "tab separated"                 KB_EMBED_MODEL 'KB_EMBED_MODEL=\ttabbed\n'
check "duplicate keys (last wins)"    KB_EMBED_MODEL 'KB_EMBED_MODEL=first\nKB_EMBED_MODEL=second\n'
check "whole-line comment ignored"    KB_EMBED_MODEL '# KB_EMBED_MODEL=commented\nKB_EMBED_MODEL=real\n'
check "inline comment stripped"       KB_EMBED_MODEL 'KB_EMBED_MODEL=value # note\n'
check "bare hash kept"                KB_EMBED_MODEL 'KB_EMBED_MODEL=va#lue\n'
check "comment after quoted value"    KB_EMBED_MODEL 'KB_EMBED_MODEL="value" # note\n'
check "trailing text after quote"     KB_EMBED_MODEL 'KB_EMBED_MODEL="value" junk\n'
check "unterminated quote"            KB_EMBED_MODEL 'KB_EMBED_MODEL="oops\n'
check "empty value"                   KB_EMBED_MODEL 'KB_EMBED_MODEL=\n'
check "colon in value"                KB_EMBED_MODEL 'KB_EMBED_MODEL=a:b:c\n'
check "equals in value"               KB_EMBED_MODEL 'KB_EMBED_MODEL=a=b=c\n'
check "command substitution literal"  KB_WEEKLY_AGENT 'KB_WEEKLY_AGENT="claude $(whoami)"\n'
check "backticks literal"             KB_WEEKLY_AGENT 'KB_WEEKLY_AGENT="claude `whoami`"\n'
check "other var not expanded"        KB_EMBED_MODEL 'KB_EMBED_MODEL=$OTHER/x\n'
check "digit-leading key rejected"    KB_EMBED_MODEL '9BAD=x\nKB_EMBED_MODEL=fine\n'
check "non-assignment line ignored"   KB_EMBED_MODEL 'this is not config\nKB_EMBED_MODEL=fine\n'
check "CRLF line endings"             KB_EMBED_MODEL 'KB_EMBED_MODEL=crlf\r\n'
check "blank lines"                   KB_EMBED_MODEL '\n\n   \nKB_EMBED_MODEL=spaced\n'
check "no trailing newline"           KB_EMBED_MODEL 'KB_EMBED_MODEL=eof'
check "unknown key ignored"           KB_EMBED_MODEL 'TOTALLY_UNKNOWN=x\nKB_EMBED_MODEL=fine\n'
check "value with spaces unquoted"    KB_WEEKLY_AGENT 'KB_WEEKLY_AGENT=claude --model opus\n'
check "leading ~/ expands"            KB_ROOT 'KB_ROOT=~/kbdir\n'
check "leading \$HOME/ expands"       KB_ROOT 'KB_ROOT=$HOME/kbdir\n'
check "leading \${HOME}/ expands"     KB_ROOT 'KB_ROOT=${HOME}/kbdir\n'
check "retriever value"               KB_RETRIEVER 'KB_RETRIEVER=semantic\n'

# Every remaining configurable key, so no setting is left unverified.
check "embed url"                     KB_EMBED_URL 'KB_EMBED_URL=http://h:1/api\n'
check "embed dim"                     KB_EMBED_DIM 'KB_EMBED_DIM=1024\n'
check "secret backend"                KB_SECRET_BACKEND 'KB_SECRET_BACKEND=macos\n'
check "secret service"                KB_SECRET_SERVICE 'KB_SECRET_SERVICE=my-svc\n'
check "python path"                   KB_PYTHON 'KB_PYTHON=/usr/bin/python3\n'
# Based on $WORK (an existing dir) rather than a literal /tmp path: path keys
# are compared after canonicalizing both sides, which needs the parent to
# exist. A hard-coded Unix "/tmp/..." also has no consistent meaning on Windows,
# where Python resolves it to "C:\\tmp\\..." while the shell keeps it literal.
check "state dir"                     KB_STATE_DIR "KB_STATE_DIR=$WORK/pch-state\n"

# Typed/normalized values must normalize identically on both sides.
check "retriever mixed case"          KB_RETRIEVER 'KB_RETRIEVER=SeMaNtIc\n'
check "retriever uppercase"           KB_RETRIEVER 'KB_RETRIEVER=KEYWORD\n'
check "embed dim non-numeric"         KB_EMBED_DIM 'KB_EMBED_DIM=oops\n'
check "embed dim negative"            KB_EMBED_DIM 'KB_EMBED_DIM=-5\n'
check "embed dim out of range"        KB_EMBED_DIM 'KB_EMBED_DIM=999999999\n'

# Both implementations must refuse the same oversized file.
big="$(head -c 70000 /dev/zero | tr '\0' '#')"
check "oversized config rejected"     KB_EMBED_MODEL "# ${big}\nKB_EMBED_MODEL=toobig\n"

# --------------------------------------------------------------------------
# Strict-mode sourcing. Every bin/ script runs `set -euo pipefail`, so
# _common.sh must survive it. This is tested separately because the value
# fixtures above source without strict mode and therefore cannot catch it --
# a real regression shipped where an unset-variable expansion under `set -u`
# killed the whole CLI, and the 44 fixtures above all still passed.
# --------------------------------------------------------------------------
echo
echo "== strict-mode sourcing (set -eu) =="
# Restore a normal config: the last fixture above deliberately leaves an
# oversized file behind, and its (correct) warning is not what we test here.
printf 'KB_EMBED_MODEL=normal\n' > "$HARNESS/config/harness.env"

# stderr is kept separate — diagnostics are allowed; a non-zero exit or missing
# stdout is not.
for shell in $SHELLS; do
  # Clean environment (nothing preset) is the case that broke.
  if out="$("$shell" -c 'set -eu; . "$1/bin/_common.sh"; printf ok' _ "$HARNESS" 2>/dev/null)" \
     && [ "$out" = "ok" ]; then
    PASS=$((PASS + 1)); printf '  ok    %-44s clean env\n' "$shell"
  else
    FAIL=$((FAIL + 1)); printf '  FAIL  %-44s clean env (exit/stdout wrong)\n' "$shell"
  fi
  # And with variables preset, which takes the other branch.
  if out="$(KB_ROOT=/x KB_RETRIEVER=semantic "$shell" -c 'set -eu; . "$1/bin/_common.sh"; printf ok' _ "$HARNESS" 2>/dev/null)" \
     && [ "$out" = "ok" ]; then
    PASS=$((PASS + 1)); printf '  ok    %-44s preset env\n' "$shell"
  else
    FAIL=$((FAIL + 1)); printf '  FAIL  %-44s preset env (exit/stdout wrong)\n' "$shell"
  fi
done

echo
echo "== CLI smoke (the entry point users actually run) =="
for sub in "--help" "health"; do
  if "$HARNESS/bin/kb" $sub >/dev/null 2>&1; then
    PASS=$((PASS + 1)); printf '  ok    kb %-41s\n' "$sub"
  else
    FAIL=$((FAIL + 1)); printf '  FAIL  kb %-41s exited %s\n' "$sub" "$?"
  fi
done

echo
echo "== summary =="
echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
