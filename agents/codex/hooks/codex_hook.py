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
    "session-start": "hooks/session_start.py",
    "user-prompt-submit": "hooks/prompt_submit.py",
    "post-tool-use": "hooks/post-tool-use-hook.sh",
    "stop": "hooks/lesson_capture.py",
}


def emit(text: str) -> None:
    """Forward hook output to Codex.

    The shared hooks already emit a JSON envelope for Claude Code. Pass that
    straight through when present rather than nesting it inside another
    envelope, and only wrap plain text.
    """
    if not text:
        return
    try:
        parsed = json.loads(text)
    except ValueError:
        print(json.dumps({"additionalContext": text}))
        return
    if isinstance(parsed, dict) and "hookSpecificOutput" in parsed:
        inner = parsed["hookSpecificOutput"].get("additionalContext", "")
        if inner:
            print(json.dumps({"additionalContext": inner}))
        return
    # Anything else (e.g. the Stop hook's {"decision": ...}) is already the
    # shape the host expects.
    print(text)


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    script = EVENT_HOOK.get(event)
    if not script:
        return 0
    raw = sys.stdin.read()
    try:
        path = os.path.join(ROOT, script)
        # Dispatch by extension: the shared hooks are Python, with one
        # remaining shell helper.
        runner = [sys.executable, path] if path.endswith(".py") else ["bash", path]
        out = subprocess.run(
            runner, input=raw, capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return 0
    emit(out.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
