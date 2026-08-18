#!/usr/bin/env python3
"""Merge this harness's hooks into ~/.claude/settings.json, safely.

This is the one install step that touches a file the user already owns and
probably already customised. Getting it wrong means clobbering their model
choice, their permissions, or hooks belonging to something else — so it is a
script with tests rather than something an agent hand-edits.

Guarantees:
  - Only the "hooks" key is touched. Every other setting is preserved byte for
    byte, including keys this script has never heard of.
  - Existing hooks for the same event are KEPT. Ours are appended.
  - Idempotent: running it twice does not duplicate entries, and re-running
    after an upgrade replaces our old entries rather than stacking new ones.
  - A timestamped backup is written before any change.
  - --uninstall removes exactly our entries and nothing else.

Ours are identified by their command containing the harness root, so a user's
own hooks are never matched by accident.

    python3 install/merge-claude-settings.py [--settings PATH] [--dry-run]
    python3 install/merge-claude-settings.py --uninstall
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# How the generated hook commands name the interpreter and the repo path, per
# OS. Claude Code runs these command strings through its own shell on each
# platform, and what is on that PATH differs:
#   - Windows ships the interpreter as `python`; there is no `python3`.
#   - `bash` is present in the hook context on every platform (Claude Code
#     requires Git Bash on Windows), so it stays literal.
#   - Paths use POSIX forward slashes via Path.as_posix(): on Unix that is the
#     native path unchanged; on Windows it yields "C:/Users/..." which both the
#     native Python interpreter AND Git Bash accept, while backslashes would
#     need escaping in JSON and would break the `bash <path>` argument.
_IS_WINDOWS = os.name == "nt"
PY = "python" if _IS_WINDOWS else "python3"
ROOT_POSIX = ROOT.as_posix()


def harness_hooks() -> dict:
    """The hook set this harness installs, with absolute paths."""
    return {
        "SessionStart": [
            {
                "matcher": "startup|resume|clear",
                "hooks": [{"type": "command", "command": f"{PY} {ROOT_POSIX}/hooks/session_start.py"}],
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {"type": "command", "command": f"{PY} {ROOT_POSIX}/hooks/prompt_submit.py"},
                    {"type": "command", "command": f"{PY} {ROOT_POSIX}/bin/credential-guard"},
                ]
            }
        ],
        "PostToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit|NotebookEdit",
                "hooks": [{"type": "command", "command": f"bash {ROOT_POSIX}/hooks/post-tool-use-hook.sh"}],
            }
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": f"{PY} {ROOT_POSIX}/hooks/lesson_capture.py"}]}
        ],
    }


def is_ours(entry: dict) -> bool:
    """Does this entry belong to this harness install?

    Matched on the harness root appearing in a command, so hooks the user wrote
    themselves — or another tool's — are never touched. Both the native spelling
    and the POSIX spelling are checked so entries written by an older install
    (or on the other path convention) are still recognized and cleanly replaced
    rather than duplicated.
    """
    needles = {str(ROOT), ROOT_POSIX}
    for hook in entry.get("hooks", []) or []:
        command = str(hook.get("command", ""))
        if any(needle in command for needle in needles):
            return True
    return False


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        sys.exit(
            f"error: {path} is not valid JSON ({exc}).\n"
            "Refusing to touch it — fix or move the file, then re-run."
        )
    if not isinstance(data, dict):
        sys.exit(f"error: {path} does not contain a JSON object; refusing to modify it.")
    return data


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    target = path.with_suffix(f".json.backup-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, target)
    return target


def merge(settings: dict, *, uninstall: bool) -> tuple[dict, int, int]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    result = dict(settings)
    added = removed = 0
    merged_hooks = {event: list(entries) for event, entries in hooks.items() if isinstance(entries, list)}

    # Always drop our previous entries first, so an upgrade replaces rather than
    # stacks, and a re-run is a no-op.
    for event, entries in list(merged_hooks.items()):
        kept = [e for e in entries if not (isinstance(e, dict) and is_ours(e))]
        removed += len(entries) - len(kept)
        if kept:
            merged_hooks[event] = kept
        else:
            del merged_hooks[event]

    if not uninstall:
        for event, entries in harness_hooks().items():
            merged_hooks.setdefault(event, [])
            merged_hooks[event].extend(entries)
            added += len(entries)

    if merged_hooks:
        result["hooks"] = merged_hooks
    else:
        result.pop("hooks", None)
    return result, added, removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    path = Path(args.settings).expanduser()
    settings = load(path)
    before = json.dumps(settings, indent=2, sort_keys=True)
    merged, added, removed = merge(settings, uninstall=args.uninstall)
    after = json.dumps(merged, indent=2, sort_keys=True)

    # Prove the blast radius: nothing outside "hooks" may change.
    untouched_before = {k: v for k, v in settings.items() if k != "hooks"}
    untouched_after = {k: v for k, v in merged.items() if k != "hooks"}
    if untouched_before != untouched_after:
        sys.exit("error: refusing to write — a non-hook setting would have changed.")

    if before == after:
        print(f"already up to date: {path}")
        return 0

    if args.dry_run:
        print(f"--dry-run: would update {path}")
        print(f"  our entries removed: {removed}, added: {added}")
        others = sum(
            len([e for e in v if not (isinstance(e, dict) and is_ours(e))])
            for v in (merged.get("hooks") or {}).values()
        )
        print(f"  hooks belonging to others, preserved: {others}")
        return 0

    saved = backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write via a temp file and replace, so an interrupted write cannot leave
    # the user with a truncated settings file.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

    action = "removed" if args.uninstall else "installed"
    print(f"{action} harness hooks in {path}")
    if saved:
        print(f"  backup: {saved}")
    print(f"  our entries removed: {removed}, added: {added}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
