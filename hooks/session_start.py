#!/usr/bin/env python3
"""SessionStart hook — prime an agent session with what is already known.

When a session opens inside a managed project, this injects the matching system
page plus every lesson that page links to, so the agent starts already knowing
the architecture, the known issues, and the mistakes already made. The "never
learn it twice" machinery has to run before the first mistake can be repeated.

Matching walks UP from the session's directory, trying each directory name as a
system slug, so a session opened deep inside a repo still finds its system page.

When nothing matches (a home directory, an unmapped project), it falls back to
the always-hot file rather than staying silent — otherwise the sessions most
likely to lack context are exactly the ones that get none.

Stdlib only, and never raises: a failure here must not stop a session opening.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

try:
    from harness_config import CONFIG, in_project_scope, is_excluded
except Exception:  # pragma: no cover
    sys.exit(0)

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")
DATED_SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# Keeps a very large system page from crowding out the actual conversation.
MAX_PAGE_CHARS = 24000


def emit(context: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }))


def slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("_", "-")


def find_system_page(start: Path) -> Path | None:
    """Walk up from `start`, matching directory names against system pages."""
    try:
        current = start.resolve()
    except OSError:
        return None
    for directory in [current, *current.parents]:
        candidate = CONFIG.systems_dir / f"{slugify(directory.name)}.md"
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
        # Stop at a project root; above it, directory names are meaningless.
        if any(directory == root for root in CONFIG.project_roots):
            break
    return None


def linked_lessons(page_text: str) -> list[str]:
    """Dated wikilinks on the page that resolve to real lesson files.

    Re-surfaced as an explicit list rather than left buried mid-page, so the
    agent treats them as first-class context it is expected to read.
    """
    found = set()
    for match in WIKILINK_RE.finditer(page_text):
        target = match.group(1).strip()
        if not DATED_SLUG_RE.match(target):
            continue
        try:
            if (CONFIG.lessons_dir / f"{target}.md").is_file():
                found.add(target)
        except OSError:
            continue
    return sorted(found, reverse=True)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    cwd = str((payload or {}).get("cwd") or os.getcwd())

    # Prime inside managed projects only, and never inside the KB itself.
    if not in_project_scope(cwd) or is_excluded(cwd):
        return 0

    page = find_system_page(Path(cwd))

    if page is not None:
        text = read(page).strip()
        if not text:
            return 0
        if len(text) > MAX_PAGE_CHARS:
            text = text[:MAX_PAGE_CHARS].rstrip() + "\n\n[system page truncated]"

        lines = [
            f"# Session context: {page.stem}",
            "",
            f"This session opened in a folder matching **{page.stem}**. The "
            "knowledge-base page for it is below — treat it as ground truth for "
            "architecture, integrations and known issues. Read the linked "
            "lessons before troubleshooting anything that resembles a past "
            "incident.",
            "",
            "---",
            "",
            text,
        ]
        lessons = linked_lessons(text)
        if lessons:
            lines += [
                "",
                "---",
                "",
                f"## Lessons linked from this page ({len(lessons)})",
                "",
                "Read these if the current work touches them:",
                "",
            ]
            lines += [f"- `{CONFIG.lessons_dir / (name + '.md')}`" for name in lessons]
        emit("\n".join(lines))
        return 0

    # No system page matched. Fall back to always-hot context so that every
    # in-scope session at least knows the KB exists and carries the top gotchas.
    hot = read(CONFIG.hot_file).strip()
    if not hot:
        return 0
    emit("\n".join([
        "# Session context: knowledge base",
        "",
        "No system page matched this folder, so the always-loaded notes are "
        f"below. The full knowledge base is at `{CONFIG.kb_root}` — read "
        "`index.md`, then `systems/<name>.md` for whatever you start working on.",
        "",
        "---",
        "",
        hot,
    ]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # pragma: no cover
        raise SystemExit(0)
