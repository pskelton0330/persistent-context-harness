#!/usr/bin/env python3
"""UserPromptSubmit hook — surface past lessons BEFORE the agent debugs.

This is the component that makes the knowledge base pay off. When you describe a
problem, matching lessons are injected as context so the agent reads what was
already learned instead of rediscovering it.

Deliberately shared by every agent (Claude Code and Codex both invoke this same
file) so they cannot drift apart. Two agents with different recall behaviour is
worse than one agent with none, because you stop being able to predict what
either of them knows.

Order of operations matters:
  1. Scope gate     — silent outside configured project roots, and inside the KB
  2. Noise gate     — skip synthetic agent plumbing, not user symptoms
  3. Credential gate— screen before anything is logged or sent to a backend
  4. Symptom gate   — only fire on problem-shaped prompts
  5. Retrieve       — semantic, falling back to keyword

Stdlib only: this runs on every user turn, so it must be fast and must never
raise. Any unexpected failure exits 0 silently — a broken hook must not be able
to block someone's prompt.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
ROOT = HOOK_DIR.parent
sys.path.insert(0, str(ROOT / "lib"))

try:
    from harness_config import CONFIG, should_retrieve
except Exception:  # pragma: no cover - never block a prompt
    sys.exit(0)

# Problem-shaped language. Tuned toward over-triggering: a spurious lesson costs
# a few tokens, while a missed one costs the whole point of the system.
SYMPTOM_PATTERNS = [
    r"\bdoesn'?t work\b", r"\bnot working\b", r"\bbroken\b",
    r"\bfail(s|ed|ing)?\b", r"\berror(s|ed|ing)?\b", r"\bcrash(es|ed|ing)?\b",
    r"\bstuck\b", r"\bhang(s|ing)?\b", r"\bfreez(es|ed|ing)?\b",
    r"\bslow\b", r"\blagg?(y|ing)?\b",
    r"\btimes? out\b", r"\btimeout(s|ed|ing)?\b",
    r"\bnever (lights?|shows?|appears?|connects?|responds?|updates?|loads?|starts?|finishes?|works?)\b",
    r"\b(stays?|remains?) (dark|off|empty|stuck|unreachable)\b",
    r"\bwrong\b", r"\bunexpected\b", r"\bmissing\b",
    r"\b(gone|empty|null|undefined|unreachable)\b",
    r"\bnot \w{3,}ing\b", r"\bstopped? \w{3,}ing\b",
    r"\bwhy (is|does|are|did|won'?t|can'?t)\b",
    r"\bregress(ion|ed)\b", r"\bflaky\b", r"\bintermittent\b",
]
SYMPTOM_RE = re.compile("|".join(SYMPTOM_PATTERNS), re.IGNORECASE)

# Screened before the prompt reaches a retriever, a log, or an embedding
# backend. UserPromptSubmit hooks can run in parallel, so this cannot rely on
# another hook having sanitized the text first.
SECRET_PATTERNS = [
    r"(?is)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----",
    r"(?im)^\s*(password|passwd|token|api[_ -]?key|secret|value)\s*[:=]\s*\S{8,}\s*$",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
]
SECRET_RE = re.compile("|".join(SECRET_PATTERNS))

MAX_PROMPT_CHARS = 8000


def emit(context: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }))


def run(cmd: list[str], timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(ROOT), env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return proc.returncode, proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def semantic(prompt: str) -> tuple[bool, str]:
    """Returns (available, output). available=False means fall back."""
    if CONFIG.retriever != "semantic":
        return False, ""
    python = CONFIG.python or sys.executable
    code, out = run(
        [python, str(ROOT / "lib" / "retrieval" / "lesson_retriever.py"), prompt], 10
    )
    # Exit 2 is the retriever's contract for "semantic unavailable or index
    # unhealthy" — the caller must fall back rather than report no lessons.
    if code == 2:
        return False, ""
    return True, out


def keyword(prompt: str) -> str:
    code, out = run([str(ROOT / "bin" / "kb"), "recall", prompt], 15)
    if code != 0 or not out or out.startswith("(no matching"):
        return ""
    return (
        "[lesson-recall] This message reads like a problem report. Lessons "
        "matching the described symptom are listed below — read them before "
        "debugging from scratch.\n\n" + out
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0

    prompt = str(payload.get("prompt") or "")
    cwd = str(payload.get("cwd") or os.getcwd())

    if not prompt.strip():
        return 0

    # 1. Scope. Silent outside managed projects, and inside the KB itself
    #    (recalling KB context into a session editing the KB is a feedback loop).
    if not should_retrieve(cwd):
        return 0

    # 2. Synthetic agent plumbing is not a user symptom; retrieving on it fills
    #    the log with noise and wastes a backend round-trip.
    stripped = prompt.lstrip().lower()
    if stripped.startswith(("<task-notification>", "<system-reminder>", "<command-name>")):
        return 0

    # 3. Credentials never reach a retriever, a log, or an embedding backend.
    if SECRET_RE.search(prompt):
        return 0

    # 4. Only problem-shaped prompts.
    if not SYMPTOM_RE.search(prompt):
        return 0

    # Long prompts are truncated for retrieval only; the symptom is nearly
    # always at the start, and the backend has a context limit.
    query = prompt[:MAX_PROMPT_CHARS]

    available, out = semantic(query)
    if available and out:
        emit(out)
        return 0

    # Semantic unavailable, or ran but found nothing. Keyword can still hit,
    # so recall degrades rather than disappearing.
    out = keyword(query)
    if out:
        emit(out)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # pragma: no cover - a hook must never block a prompt
        raise SystemExit(0)
