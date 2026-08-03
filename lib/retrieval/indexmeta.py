#!/usr/bin/env python3
"""Index provenance and integrity, shared by the indexer and the retriever.

Both sides must agree on what makes an index trustworthy, so the schema version,
the content fingerprint and the row-integrity check live here rather than being
implemented twice.

Stdlib only (no `requests`, no `sqlite_vec`) so the retriever can import it even
when the optional extras are missing.
"""

from __future__ import annotations

import hashlib
import sqlite3
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness_config import CONFIG  # noqa: E402

# Bump when the on-disk layout changes in a way that makes an older index
# unusable. The retriever refuses to query a mismatched schema.
SCHEMA_VERSION = 1


def lesson_paths(lessons_dir: Path | None = None) -> list[Path]:
    """The lessons an index should contain.

    Filters to REGULAR FILES: a directory named `something.md` matches the glob
    and stats fine but cannot be read, so counting it would leave a "healthy"
    index that silently omitted a lesson.

    Enumeration FAILS CLOSED -- every OSError propagates. `Path.is_file()` and a
    caught glob error both turn a permissions or filesystem fault into an empty
    list, and an empty list is indistinguishable from "the user deleted all
    their lessons": a build would then replace a good index with an empty one
    and destroy all semantic recall. Callers must treat a raised OSError as
    "cannot determine the lesson set" and leave existing state untouched.
    """
    directory = lessons_dir or CONFIG.lessons_dir
    found: list[Path] = []
    # glob() defers directory reads, so an unsearchable directory raises here
    # rather than yielding nothing.
    for path in sorted(directory.glob("*.md")):
        # stat() rather than is_file(), which swallows OSError and returns False.
        if stat.S_ISREG(path.stat().st_mode):
            found.append(path)
    return found


def lesson_fingerprint(paths: list[Path]) -> str:
    """Identity of the lesson set an index was built from.

    Replaces comparing a wall-clock `indexed_at` against file mtimes, which was
    racy in both directions: a lesson edited mid-build could look older than the
    final stamp (a stale index reported healthy), while sub-second mtime
    resolution could make a just-built index look stale immediately.

    Captured BEFORE the files are read and compared against a live recomputation
    at query time, so anything that changes during a build shows up as a
    mismatch -- erring toward a needless rebuild rather than serving embeddings
    that no longer match their source.

    CONTRACT: this is a cheap identity over (relative path, mtime_ns, size), not
    a content hash. It detects any ordinary edit, rename, addition or removal.
    It does NOT detect a rewrite that deliberately preserves both mtime and size
    (e.g. `touch -r`). Hashing file bytes would be exact but would mean reading
    every lesson on every query; the stat form keeps the query path cheap. A
    path that cannot be statted raises, so a partial scan can never produce the
    same digest as a complete one.
    """
    digest = hashlib.sha256()
    for path in sorted(paths):
        # Deliberately not swallowing OSError: silently skipping an unreadable
        # entry could yield the same digest as a complete scan.
        # Named `info`, not `stat`, so it cannot shadow the stat module.
        info = path.stat()
        try:
            name = str(path.resolve().relative_to(CONFIG.kb_root))
        except (OSError, ValueError):
            name = path.name
        digest.update(name.encode("utf-8", "replace"))
        digest.update(b"\0")
        digest.update(str(info.st_mtime_ns).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(info.st_size).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def current_fingerprint() -> str:
    """Live fingerprint, or "" if it cannot be computed.

    An empty string never equals a stored fingerprint, so an unreadable lessons
    directory surfaces as "stale" and falls back to keyword recall rather than
    being treated as unchanged.
    """
    try:
        return lesson_fingerprint(lesson_paths())
    except OSError:
        return ""


def rowid_integrity(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Every lesson has exactly one vector, and vice versa.

    Comparing counts alone is not enough: deleting one vector row and inserting
    an orphan elsewhere keeps the totals equal while silently dropping a lesson
    from the join, so it could never be retrieved again.
    """
    try:
        missing = conn.execute(
            "SELECT COUNT(*) FROM (SELECT id FROM lessons EXCEPT SELECT rowid FROM vec_lessons)"
        ).fetchone()[0]
        orphaned = conn.execute(
            "SELECT COUNT(*) FROM (SELECT rowid FROM vec_lessons EXCEPT SELECT id FROM lessons)"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
    except sqlite3.Error as exc:
        return False, f"index unreadable ({exc})"
    if missing:
        return False, f"{missing} lesson(s) have no vector"
    if orphaned:
        return False, f"{orphaned} orphaned vector row(s)"
    if total == 0:
        return False, "index is empty"
    return True, "ok"
