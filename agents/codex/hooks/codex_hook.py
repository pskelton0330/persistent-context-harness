#!/usr/bin/env python3
"""Codex hook shim → shared shell hooks.

Codex hooks.json maps each event to:  python3 .../codex_hook.py <event>
This reads the hook payload on stdin, runs the matching shell hook, and prints
any output back as Codex's additionalContext envelope. Keeps one source of truth
(the hooks/ shell scripts) shared with Claude Code.

If your Codex version expects a different output envelope, adjust `emit()` below.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))            # agents/codex/hooks
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # repo root

EVENT_HOOK = {
    "session-start": "hooks/session-start-hook.sh",
    "user-prompt-submit": "hooks/symptom-lesson-retriever.sh",
    "post-tool-use": "hooks/post-tool-use-hook.sh",
    "stop": "hooks/lesson-capture-hook.sh",
}


def emit(text: str) -> None:
    if text:
        print(json.dumps({"additionalContext": text}))


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    script = EVENT_HOOK.get(event)
    if not script:
        return 0
    raw = sys.stdin.read()
    try:
        out = subprocess.run(
            ["bash", os.path.join(ROOT, script)],
            input=raw, capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return 0
    emit(out.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
