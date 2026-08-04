#!/usr/bin/env bash
# Weekly self-improvement pass over the knowledge base.
#
# Capture makes the KB grow; this keeps it worth reading. Without it a KB slowly
# fills with duplicates, half-written entries, and lessons nothing ever links to,
# and recall quality decays even as the lesson count climbs.
#
# Deterministic steps run locally. The steps that need judgement are handed to
# an agent CLI (KB_WEEKLY_AGENT, default `claude`) rather than a pinned local
# model — pinning a model tag is fragile: if it is renamed or removed the job
# fails soft and can stay broken for weeks without anyone noticing.
#
# Output is DRAFTS plus a report, never direct edits to the knowledge base. A
# job that rewrites your notes unattended is not something to run on a schedule.
# Review the report, apply what you agree with.
#
#   bash weekly/run-weekly.sh            # full pass
#   bash weekly/run-weekly.sh --no-agent # deterministic steps only
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
. "$ROOT/bin/_common.sh"

USE_AGENT=1
[ "${1:-}" = "--no-agent" ] && USE_AGENT=0

STAMP="$(date +%Y-%m-%d)"
OUT_DIR="$KB_STATE_DIR/weekly/$STAMP"
LOG="$OUT_DIR/run.log"
STATUS="$KB_STATE_DIR/weekly/last-run.json"
mkdir -p "$OUT_DIR"

FAILED=0
STEPS_OK=""
STEPS_FAILED=""

say() { printf '%s\n' "$*" | tee -a "$LOG"; }

step() {
  local name="$1"; shift
  say ""
  say "---- $name ----"
  if "$@" >>"$LOG" 2>&1; then
    say "[$name] ok"
    STEPS_OK="$STEPS_OK $name"
  else
    say "[$name] FAILED (continuing)"
    STEPS_FAILED="$STEPS_FAILED $name"
    FAILED=$((FAILED + 1))
  fi
}

say "weekly knowledge-base review — $(date)"
say "kb:    $KB_ROOT"
say "out:   $OUT_DIR"

# ---------------------------------------------------------------------------
# Deterministic steps
# ---------------------------------------------------------------------------
# Reindex only when semantic search is both configured AND actually installed.
#
# The distinction is capability, not configuration: KB_RETRIEVER defaults to
# semantic, so keying off it alone reports a FAILED step on every install where
# the extras were never added — a capability that was never present has not
# broken. That kind of false alarm is corrosive here specifically, because this
# job's whole value rests on a failure report being believed.
#
# A build that fails when the extras ARE present is a real failure and stays loud.
semantic_available() {
  [ "$KB_RETRIEVER" = "semantic" ] || return 1
  local py="${KB_PYTHON:-python3}"
  command -v "$py" >/dev/null 2>&1 || return 1
  "$py" -c 'import requests, sqlite_vec' >/dev/null 2>&1
}

if semantic_available; then
  step reindex "$ROOT/bin/kb" index --incremental
else
  say ""
  say "---- reindex ----"
  if [ "$KB_RETRIEVER" = "semantic" ]; then
    say "[reindex] skipped — semantic configured but extras not installed."
    say "          Recall is running in keyword mode. Fix: bash install/install-extras.sh"
  else
    say "[reindex] skipped (KB_RETRIEVER=$KB_RETRIEVER, no semantic index)"
  fi
fi

retrieval_stats() {
  local py="${KB_PYTHON:-python3}"
  "$py" "$ROOT/lib/retrieval/retrieval_log.py" --days 30 --json > "$OUT_DIR/retrieval-stats.json"
  "$py" "$ROOT/lib/retrieval/retrieval_log.py" --days 30
}
step retrieval-stats retrieval_stats

structure_check() {
  "$ROOT/bin/kb" health > "$OUT_DIR/structure.txt" 2>&1 || true
  cat "$OUT_DIR/structure.txt"
}
step structure-check structure_check

# ---------------------------------------------------------------------------
# Agent steps
# ---------------------------------------------------------------------------
# Each gets a focused prompt and writes ONE draft file. Kept separate so a
# failure in one does not lose the others, and so each draft is reviewable on
# its own terms.
run_agent() {
  local name="$1" prompt_file="$2" out_file="$3"
  local agent="${KB_WEEKLY_AGENT:-claude}"
  local bin="${agent%% *}"

  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "agent CLI '$bin' not on PATH" >&2
    return 1
  fi

  # Context the prompt needs, assembled here so the agent does not have to
  # discover the layout itself.
  {
    sed -e "s#__KB_ROOT__#$KB_ROOT#g" \
        -e "s#__OUT__#$out_file#g" \
        -e "s#__STATS__#$OUT_DIR/retrieval-stats.json#g" \
        -e "s#__STRUCTURE__#$OUT_DIR/structure.txt#g" \
        "$prompt_file"
  } | $agent -p >"$out_file.raw" 2>"$out_file.err"
  local rc=$?

  if [ $rc -ne 0 ]; then
    echo "agent exited $rc; stderr:" >&2
    head -20 "$out_file.err" >&2
    return 1
  fi
  if [ ! -s "$out_file.raw" ]; then
    echo "agent produced no output" >&2
    return 1
  fi
  mv "$out_file.raw" "$out_file"
  rm -f "$out_file.err"
  echo "wrote $out_file"
}

if [ "$USE_AGENT" = "1" ]; then
  step lesson-audit  run_agent lesson-audit  "$HERE/prompts/lesson-audit.md"  "$OUT_DIR/lesson-audit.md"
  step crosslinks    run_agent crosslinks    "$HERE/prompts/crosslinks.md"    "$OUT_DIR/crosslinks.md"
  step gap-review    run_agent gap-review    "$HERE/prompts/gap-review.md"    "$OUT_DIR/gap-review.md"
else
  say ""
  say "---- agent steps skipped (--no-agent) ----"
fi

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
# Written every run, success or failure, and read by `kb health` and
# kb-selftest. A scheduled job that fails quietly is worse than no job: the
# whole point is that you find out.
cat > "$STATUS" <<EOF
{
  "ran_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "output_dir": "$OUT_DIR",
  "failed_steps": $FAILED,
  "ok": "${STEPS_OK# }",
  "failed": "${STEPS_FAILED# }",
  "agent": "${KB_WEEKLY_AGENT:-claude}",
  "used_agent": $USE_AGENT
}
EOF

say ""
say "================================================================"
if [ "$FAILED" -gt 0 ]; then
  say "COMPLETED WITH $FAILED FAILED STEP(S):${STEPS_FAILED}"
  say "Full log: $LOG"
else
  say "All steps completed."
fi
say ""
say "Review queue:"
for f in "$OUT_DIR"/*.md; do
  [ -e "$f" ] && say "  $f"
done
say "  stats: $OUT_DIR/retrieval-stats.json"
say "================================================================"

exit "$([ "$FAILED" -gt 0 ] && echo 1 || echo 0)"
