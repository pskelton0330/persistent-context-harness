#!/usr/bin/env python3
"""Stop hook — capture a lesson after real engineering work.

Closes the loop: priming and recall only pay off if new knowledge keeps arriving.
This fires when a session actually edited files in a managed project and asks the
agent to judge whether something durable was learned.

Gating is deliberate. It fires:
  - only when files were edited in a configured project root,
  - never for edits confined to the KB itself (writing notes is not a lesson),
  - at most ONCE per session, so the workflow stays hands-off.

Bias is toward capturing. A weak lesson is one `git revert` away; a lesson never
written is lost for good. That asymmetry is why this asks rather than nags, and
why it does not demand confirmation first.

Stdlib only, and never raises.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

try:
    from harness_config import CONFIG, in_project_scope, is_excluded, under
except Exception:  # pragma: no cover
    sys.exit(0)

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch"}

# Transcripts can be large; only the tail is scanned for edit activity.
MAX_TRANSCRIPT_BYTES = 8 * 1024 * 1024


def marker(session_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"pch-lesson-{session_id}.fired"


def edited_project_files(transcript: Path) -> bool:
    """Did this session edit a file in a managed project (not the KB)?"""
    try:
        size = transcript.stat().st_size
        with transcript.open(encoding="utf-8", errors="replace") as handle:
            if size > MAX_TRANSCRIPT_BYTES:
                handle.seek(size - MAX_TRANSCRIPT_BYTES)
                handle.readline()  # discard the partial line
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                content = entry.get("message", {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    if block.get("name") not in EDIT_TOOLS:
                        continue
                    target = (block.get("input") or {}).get("file_path") or ""
                    if not target:
                        continue
                    # Editing the KB is note-taking, not the work a lesson
                    # should be written about.
                    if under(target, CONFIG.kb_root):
                        continue
                    if in_project_scope(target):
                        return True
    except OSError:
        return False
    return False


PROMPT = """\
Lesson capture. You edited files in a managed project this session. Decide \
whether something durable was learned, and act without asking.

Capture if ANY of these apply:
- a non-trivial bug fix (slow to diagnose, or the cause was surprising)
- a config gotcha, hardware quirk, or undocumented API behaviour
- a design decision whose rationale is not obvious from the code
- anything future-you would thank past-you for having written down

If it qualifies:
1. Check for duplicates first: `{root}/bin/kb recall "<keywords>"`.
2. Create it: `{root}/bin/kb lesson "<short title>"`, then fill in every \
section — Symptom, Root cause, Fix, Prevention, References. A lesson missing \
Root cause or Prevention is not worth keeping.
3. Link it from the relevant `systems/<name>.md` page with a `[[wikilink]]`, \
otherwise session priming will never surface it.
4. Rebuild the index so it becomes searchable: `{root}/bin/kb index --incremental`.
5. Tell the user in one sentence what you captured.

If nothing qualifies, reply exactly: no lesson

Write only inside {kb}. Do not modify project code during capture.\
"""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0

    # Set when this hook's own block is being processed; continuing would loop.
    if payload.get("stop_hook_active"):
        return 0

    cwd = str(payload.get("cwd") or os.getcwd())
    if not in_project_scope(cwd) or is_excluded(cwd):
        return 0

    session_id = str(payload.get("session_id") or "")
    transcript = str(payload.get("transcript_path") or "")
    if not session_id or not transcript:
        return 0

    fired = marker(session_id)
    try:
        if fired.exists():
            return 0
    except OSError:
        return 0

    if not edited_project_files(Path(transcript)):
        return 0

    try:
        fired.touch()
    except OSError:
        pass  # worst case the nudge repeats; better than losing it entirely

    print(json.dumps({
        "decision": "block",
        "reason": PROMPT.format(root=ROOT, kb=CONFIG.kb_root),
    }))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # pragma: no cover
        raise SystemExit(0)
