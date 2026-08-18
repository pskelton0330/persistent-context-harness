#!/usr/bin/env bash
# Behavioural tests for the three agent hooks.
#
# These drive the hooks with real payloads on stdin and assert on what comes
# back. They exist because the hooks are the only components that change what an
# agent does in a session — everything else is a CLI you have to remember to run.
#
# IMPORTANT: every assertion checks the EXIT CODE and STDERR, not just whether
# stdout was empty. An earlier version of this test treated "no output" as
# "correctly stayed silent", and so scored a hook that crashed on import as five
# consecutive passes. Silence and failure look identical from stdout alone.
#
#   bash tests/test_hooks.sh
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The interpreter is python3 on Unix, python on Windows (no python3 there).
if command -v python3 >/dev/null 2>&1; then PYBIN=python3
elif command -v python >/dev/null 2>&1; then PYBIN=python
else echo "no python interpreter found" >&2; exit 1; fi

# On Windows the hooks run under native Python, which cannot resolve an MSYS
# path like /tmp/... to the directory Git Bash actually created. Re-spell the
# workspace as a Windows path both sides agree on (forward slashes: valid for
# Git Bash AND native Python). cygpath exists only under MSYS/Cygwin, so this is
# a no-op everywhere else. The EXIT trap expands $WORK lazily, so it cleans up
# the re-spelled path — the same directory — correctly.
if command -v cygpath >/dev/null 2>&1; then WORK="$(cygpath -m "$WORK")"; fi

KB="$WORK/kb"
PROJECT="$WORK/project"
mkdir -p "$KB/lessons" "$KB/systems" "$PROJECT/sub"

export KB_ROOT="$KB"
export KB_PROJECT_ROOTS="$PROJECT"
export KB_STATE_DIR="$WORK/state"
export KB_RETRIEVER=keyword   # no embedding backend needed for behaviour tests

# lesson_capture marks "already fired" with a file keyed by session id, under
# the system temp dir. Point TMPDIR at this run's workspace so those markers do
# not survive into the next run — with fixed session ids in the fixtures below,
# a leftover marker makes the once-per-session test fail on every run after the
# first, which looks like a code regression and is not one.
export TMPDIR="$WORK/tmp"
mkdir -p "$TMPDIR"

cat > "$KB/systems/project.md" <<'EOF'
# project

A service that talks to Postgres.

## Known issues
- Pool exhaustion under load; see [[2024-01-01-pool-exhaustion]].
EOF

cat > "$KB/lessons/2024-01-01-pool-exhaustion.md" <<'EOF'
---
type: lesson
date: 2024-01-01
---
# Connection pool exhaustion under load

## Symptom
Requests time out once concurrency passes 50.

## Root cause
Pool size left at the default of 5.

## Fix
Raise pool size and add a timeout.

## Prevention
Load-test before release.
EOF

cat > "$KB/hot.md" <<'EOF'
# Always-hot notes
- Check the pool size before blaming the database.
EOF

PASS=0; FAIL=0

# run <hook> <json>  -> sets OUT, ERR, RC
run_hook() {
  local hook="$1" payload="$2"
  OUT="$(printf '%s' "$payload" | "$PYBIN" "$REPO/hooks/$hook" 2>"$WORK/stderr")"
  RC=$?
  ERR="$(cat "$WORK/stderr")"
}

# Every assertion goes through here so a crash can never be read as success.
assert() {
  local label="$1" condition="$2"
  if [ "$RC" -ne 0 ] || [ -n "$ERR" ]; then
    FAIL=$((FAIL + 1))
    printf '  FAIL  %-52s (exit=%s%s)\n' "$label" "$RC" \
      "$([ -n "$ERR" ] && printf ', stderr: %.60s' "$ERR")"
    return
  fi
  if [ "$condition" = "true" ]; then
    PASS=$((PASS + 1)); printf '  ok    %-52s\n' "$label"
  else
    FAIL=$((FAIL + 1)); printf '  FAIL  %-52s\n' "$label"
  fi
}

has()   { case "$OUT" in *"$1"*) echo true ;; *) echo false ;; esac; }
empty() { [ -z "$OUT" ] && echo true || echo false; }

echo "== session_start.py =="
run_hook session_start.py "{\"cwd\":\"$PROJECT\"}"
assert "primes the matching system page"        "$(has 'Session context: project')"
run_hook session_start.py "{\"cwd\":\"$PROJECT\"}"
assert "surfaces lessons linked from that page" "$(has 'Lessons linked from this page')"
run_hook session_start.py "{\"cwd\":\"$PROJECT/sub\"}"
assert "matches from a nested directory"        "$(has 'Session context: project')"
run_hook session_start.py "{\"cwd\":\"$WORK\"}"
assert "silent outside project roots"           "$(empty)"
run_hook session_start.py "{\"cwd\":\"$KB\"}"
assert "silent inside the KB itself"            "$(empty)"

echo
echo "== prompt_submit.py =="
run_hook prompt_submit.py "{\"cwd\":\"$PROJECT\",\"prompt\":\"requests time out under load\"}"
assert "recalls on a problem-shaped prompt"     "$(has 'lesson-recall')"
run_hook prompt_submit.py "{\"cwd\":\"$PROJECT\",\"prompt\":\"requests time out under load\"}"
assert "  names the relevant lesson"            "$(has 'pool-exhaustion')"
run_hook prompt_submit.py "{\"cwd\":\"$PROJECT\",\"prompt\":\"add a docstring to the helper\"}"
assert "silent on a non-problem prompt"         "$(empty)"
run_hook prompt_submit.py "{\"cwd\":\"$WORK\",\"prompt\":\"everything is broken and times out\"}"
assert "silent outside project roots"           "$(empty)"
run_hook prompt_submit.py "{\"cwd\":\"$KB\",\"prompt\":\"this is broken and failing\"}"
assert "silent inside the KB (no feedback loop)" "$(empty)"
run_hook prompt_submit.py "{\"cwd\":\"$PROJECT\",\"prompt\":\"it fails, password: hunter2supersecret\"}"
assert "silent when the prompt holds a secret"  "$(empty)"
run_hook prompt_submit.py "{\"cwd\":\"$PROJECT\",\"prompt\":\"it fails, key AKIAIOSFODNN7EXAMPLE\"}"
assert "  also for an AWS key"                  "$(empty)"
run_hook prompt_submit.py "{\"cwd\":\"$PROJECT\",\"prompt\":\"<task-notification>job failed</task-notification>\"}"
assert "silent on synthetic agent plumbing"     "$(empty)"
run_hook prompt_submit.py "{\"cwd\":\"$PROJECT\",\"prompt\":\"\"}"
assert "silent on an empty prompt"              "$(empty)"
run_hook prompt_submit.py "not json at all"
assert "survives malformed payload"             "$(empty)"

echo
echo "== lesson_capture.py =="
TRANSCRIPT="$WORK/transcript.jsonl"
edit_entry() {
  printf '{"message":{"content":[{"type":"tool_use","name":"Edit","input":{"file_path":"%s"}}]}}\n' "$1"
}

edit_entry "$PROJECT/app.py" > "$TRANSCRIPT"
run_hook lesson_capture.py "{\"cwd\":\"$PROJECT\",\"session_id\":\"s1\",\"transcript_path\":\"$TRANSCRIPT\"}"
assert "fires after editing project files"      "$(has 'Lesson capture')"
run_hook lesson_capture.py "{\"cwd\":\"$PROJECT\",\"session_id\":\"s1\",\"transcript_path\":\"$TRANSCRIPT\"}"
assert "fires at most once per session"         "$(empty)"

edit_entry "$KB/lessons/note.md" > "$TRANSCRIPT"
run_hook lesson_capture.py "{\"cwd\":\"$PROJECT\",\"session_id\":\"s2\",\"transcript_path\":\"$TRANSCRIPT\"}"
assert "does not fire for KB-only edits"        "$(empty)"

printf '{"message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"%s"}}]}}\n' "$PROJECT/app.py" > "$TRANSCRIPT"
run_hook lesson_capture.py "{\"cwd\":\"$PROJECT\",\"session_id\":\"s3\",\"transcript_path\":\"$TRANSCRIPT\"}"
assert "does not fire when nothing was edited"  "$(empty)"

edit_entry "$PROJECT/app.py" > "$TRANSCRIPT"
run_hook lesson_capture.py "{\"cwd\":\"$PROJECT\",\"session_id\":\"s4\",\"transcript_path\":\"$TRANSCRIPT\",\"stop_hook_active\":true}"
assert "does not re-enter its own block"        "$(empty)"
run_hook lesson_capture.py "{\"cwd\":\"$WORK\",\"session_id\":\"s5\",\"transcript_path\":\"$TRANSCRIPT\"}"
assert "silent outside project roots"           "$(empty)"

echo
echo "== summary =="
echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
