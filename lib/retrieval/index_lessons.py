#!/usr/bin/env python3
"""Embed every lesson into a sqlite-vec index for semantic recall.

Semantic search exists because keyword overlap false-positives badly on generic
technical words ("turn", "work", "rate", "specific") that appear in almost any
lesson, so an unrelated lesson surfaces on nearly every problem report. Matching
on meaning fixes that.

Embedding text per lesson = title + Symptom + Root cause — the sections that
actually describe "what does this lesson cover". Long operational histories in
the Fix section only add noise, and can overflow the embedding context window.

Usage:
    kb index              # full rebuild
    kb index --incremental  # only new/changed lessons

Requires the extras (`requests`, `sqlite-vec`) and a reachable embedding
backend; see config/harness.env.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_config import CONFIG  # noqa: E402
from indexmeta import (  # noqa: E402
    SCHEMA_VERSION,
    lesson_fingerprint,
    lesson_paths,
    rowid_integrity,
)
from vectors import VectorError, floats_to_bytes, validate_batch  # noqa: E402

try:
    import requests
    import sqlite_vec
except ImportError as exc:  # pragma: no cover - dependency guidance
    sys.exit(
        f"missing dependency: {exc.name}\n"
        "The semantic index needs the extras. Install them with:\n"
        "    bash install/install-extras.sh\n"
        "or set KB_RETRIEVER=keyword in config/harness.env to skip semantic search."
    )

MAX_EMBED_CHARS = 6000
BATCH_SIZE = 16


class BuildError(RuntimeError):
    """The index cannot be built completely, so nothing is published.

    Publishing a partial index is worse than failing: the stored fingerprint
    would claim the index matches the lessons on disk while a lesson is
    silently missing, and recall would quietly lose it forever.
    """


H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
SECTION_RE_TPL = r"^##\s+{name}.*?(?=^## |\Z)"
FRONTMATTER_NAME = re.compile(r"^---\s*\n.*?\bname:\s*(.+?)\n.*?\n---", re.DOTALL)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_title(text: str) -> str:
    fm = FRONTMATTER_NAME.search(text)
    if fm:
        return fm.group(1).strip()
    h1 = H1_RE.search(text)
    return h1.group(1).strip() if h1 else ""


def extract_section(text: str, name: str) -> str:
    pattern = re.compile(
        SECTION_RE_TPL.format(name=name), re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    match = pattern.search(text)
    return match.group(0).strip() if match else ""


def clamp(text: str) -> str:
    """Keep inputs under the embedding model's context window.

    Ollama returns HTTP 400 when an input exceeds the model context length, so
    an over-long lesson would otherwise fail the whole batch.
    """
    text = text.strip()
    if len(text) <= MAX_EMBED_CHARS:
        return text
    return text[:MAX_EMBED_CHARS].rstrip() + "\n\n[embedding text truncated]"


def embed_text(text: str, fallback_title: str = "") -> str:
    title = extract_title(text) or fallback_title
    symptom = extract_section(text, "Symptom")
    cause = extract_section(text, "Root cause")

    if symptom or cause:
        parts = [f"TITLE: {title}"] if title else []
        parts.extend(part for part in (symptom, cause) if part)
        return clamp("\n\n".join(parts))

    # Unstructured or imported lessons have no sections. A title alone is a poor
    # semantic representation, so fall back to the document head.
    head = text[:1500].strip()
    return clamp(f"TITLE: {title}\n\n{head}" if title else head)


# ---------------------------------------------------------------------------
# Embedding backend
# ---------------------------------------------------------------------------


def _post(payload, timeout: int, expected_count: int):
    response = requests.post(CONFIG.embed_url, json=payload, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or "embeddings" not in body:
        raise VectorError("backend response has no 'embeddings' field")
    return validate_batch(body["embeddings"], expected_count, CONFIG.embed_dim)


def embed_one(text: str) -> list[float]:
    return _post({"model": CONFIG.embed_model, "input": text}, 60, 1)[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _post({"model": CONFIG.embed_model, "input": texts}, 120, len(texts))


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    return conn


def reset_schema(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS lessons")
    conn.execute("DROP TABLE IF EXISTS vec_lessons")
    conn.execute("DROP TABLE IF EXISTS meta")
    conn.execute(
        """
        CREATE TABLE lessons (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            path       TEXT NOT NULL UNIQUE,   -- relative to KB_ROOT
            title      TEXT NOT NULL DEFAULT '',
            embed_text TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(f"CREATE VIRTUAL TABLE vec_lessons USING vec0(embedding float[{CONFIG.embed_dim}])")
    # Records which model/dimension built this index. Without it, changing
    # KB_EMBED_MODEL leaves a stale index that returns confidently wrong
    # neighbours (or a dimension error) with no explanation.
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()


def write_meta(conn: sqlite3.Connection, fingerprint: str) -> None:
    for key, value in (
        ("schema_version", str(SCHEMA_VERSION)),
        ("embed_model", CONFIG.embed_model),
        ("embed_dim", str(CONFIG.embed_dim)),
        ("kb_root", str(CONFIG.kb_root)),
        ("indexed_at", str(int(time.time()))),
        # Identity of the source lessons, captured BEFORE reading them.
        ("lesson_fingerprint", fingerprint),
    ):
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    conn.commit()


def rel(path: Path) -> str:
    """Store paths relative to KB_ROOT so the index survives a KB move.

    A lesson resolving outside KB_ROOT (via a symlink, say) is rejected rather
    than stored absolute: mixing absolute and relative rows defeats the move
    portability the relative form exists for, and hides a violated assumption.
    """
    try:
        return str(path.resolve().relative_to(CONFIG.kb_root))
    except ValueError as exc:
        raise ValueError(
            f"lesson resolves outside KB_ROOT and cannot be indexed: {path}"
        ) from exc


def index_is_compatible(db_path: Path) -> tuple[bool, str]:
    """Can we safely add to this existing index, or must it be rebuilt?

    Incremental indexing only re-embeds CHANGED lessons. If the model or
    dimension changed, the untouched rows still hold vectors from the old model
    while the metadata would be restamped with the new one -- producing an index
    that claims to be compatible but mixes two vector spaces.
    """
    try:
        conn = open_db(db_path)
    except sqlite3.Error as exc:
        return False, f"cannot open index ({exc})"
    try:
        meta = {key: value for key, value in conn.execute("SELECT key, value FROM meta")}
        integral, reason = rowid_integrity(conn)
    except sqlite3.Error as exc:
        return False, f"index schema unreadable ({exc})"
    finally:
        conn.close()

    if meta.get("schema_version") != str(SCHEMA_VERSION):
        return False, f"schema version {meta.get('schema_version')} != {SCHEMA_VERSION}"
    if meta.get("embed_model") != CONFIG.embed_model:
        return False, f"built with model {meta.get('embed_model')!r}, now {CONFIG.embed_model!r}"
    if meta.get("embed_dim") != str(CONFIG.embed_dim):
        return False, f"built with dim {meta.get('embed_dim')}, now {CONFIG.embed_dim}"
    if meta.get("kb_root") != str(CONFIG.kb_root):
        return False, f"built against a different KB ({meta.get('kb_root')})"
    if not integral:
        return False, reason
    return True, "compatible"


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def incremental_index(paths: list[Path], fingerprint: str) -> int:
    if not CONFIG.index_db.exists():
        raise RuntimeError(f"incremental index requires an existing DB: {CONFIG.index_db}")

    conn = open_db(CONFIG.index_db)
    try:
        existing = {
            path: (row_id, title, text)
            for row_id, path, title, text in conn.execute(
                "SELECT id, path, title, embed_text FROM lessons"
            )
        }
        # As in full_index: no skipping. An unreadable lesson here is worse,
        # because the previous vector would be retained while the new
        # fingerprint is committed -- an index stamped fresh but serving a stale
        # embedding.
        usable: list[tuple[Path, str]] = []
        for path in paths:
            try:
                usable.append((path, rel(path)))
            except ValueError as exc:
                raise BuildError(f"cannot index {path}: {exc}") from exc
        current = {key for _, key in usable}
        removed = sorted(set(existing) - current)

        changed: list[tuple[str, str, str, int | None]] = []
        for path, key in usable:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                raise BuildError(f"cannot index {path}: {exc}") from exc
            title = extract_title(text) or path.stem
            indexed = embed_text(text, path.stem)
            prior = existing.get(key)
            if prior is None or prior[1] != title or prior[2] != indexed:
                changed.append((key, title, indexed, prior[0] if prior else None))

        embedded = []
        for offset in range(0, len(changed), BATCH_SIZE):
            batch = changed[offset : offset + BATCH_SIZE]
            embedded.extend(zip(batch, embed_batch([row[2] for row in batch])))

        conn.execute("BEGIN")
        for path in removed:
            row_id = existing[path][0]
            conn.execute("DELETE FROM vec_lessons WHERE rowid = ?", (row_id,))
            conn.execute("DELETE FROM lessons WHERE id = ?", (row_id,))

        for (path, title, indexed, row_id), vector in embedded:
            if row_id is None:
                cur = conn.execute(
                    "INSERT INTO lessons (path, title, embed_text) VALUES (?, ?, ?)",
                    (path, title, indexed),
                )
                row_id = cur.lastrowid
            else:
                conn.execute("DELETE FROM vec_lessons WHERE rowid = ?", (row_id,))
                conn.execute(
                    "UPDATE lessons SET title = ?, embed_text = ? WHERE id = ?",
                    (title, indexed, row_id),
                )
            conn.execute(
                "INSERT INTO vec_lessons (rowid, embedding) VALUES (?, ?)",
                (row_id, floats_to_bytes(vector)),
            )
        conn.commit()
        write_meta(conn, fingerprint)
        print(
            f"incremental index: {len(changed)} updated, {len(removed)} removed, "
            f"{len(paths)} total"
        )
        return len(paths)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def full_index(paths: list[Path], fingerprint: str) -> int:
    # Build into a temp file and swap, so an interrupted rebuild never leaves a
    # half-populated index that silently under-returns.
    tmp = CONFIG.index_db.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)

    conn = open_db(tmp)
    reset_schema(conn)
    started = time.time()
    pending: list[tuple[str, str, str]] = []

    def flush(rows: list[tuple[str, str, str]]) -> None:
        if not rows:
            return
        try:
            vectors = embed_batch([row[2] for row in rows])
        except requests.HTTPError as exc:
            # One oversized lesson fails the whole batch; retry individually so
            # a single bad document cannot block the entire index.
            print(f"  batch embed failed ({exc}); retrying {len(rows)} individually", file=sys.stderr)
            vectors = []
            for path, _title, text in rows:
                try:
                    vectors.append(embed_one(text))
                except requests.HTTPError as item_exc:
                    raise RuntimeError(
                        f"embedding failed for {path} ({len(text)} chars): {item_exc}"
                    ) from item_exc
        for (path, title, text), vector in zip(rows, vectors):
            cur = conn.execute(
                "INSERT INTO lessons (path, title, embed_text) VALUES (?, ?, ?)",
                (path, title, text),
            )
            conn.execute(
                "INSERT INTO vec_lessons (rowid, embedding) VALUES (?, ?)",
                (cur.lastrowid, floats_to_bytes(vector)),
            )
        conn.commit()

    for path in paths:
        # Deliberately NOT skipping on error. The fingerprint stored with this
        # index describes exactly this list of lessons, so quietly omitting one
        # would publish an index that claims to be complete while a lesson is
        # permanently unretrievable. Fail the build instead.
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            key = rel(path)
        except (OSError, ValueError) as exc:
            raise BuildError(f"cannot index {path}: {exc}") from exc
        pending.append((key, extract_title(text) or path.stem, embed_text(text, path.stem)))
        if len(pending) >= BATCH_SIZE:
            flush(pending)
            pending = []
    flush(pending)

    count = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
    write_meta(conn, fingerprint)
    conn.close()
    tmp.replace(CONFIG.index_db)
    print(f"indexed {count} lessons in {time.time() - started:.1f}s -> {CONFIG.index_db}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or refresh the lesson embedding index.")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="embed only new or changed lessons and drop deleted ones",
    )
    args = parser.parse_args()

    if not CONFIG.lessons_dir.is_dir():
        sys.exit(f"lessons dir not found: {CONFIG.lessons_dir}")
    CONFIG.index_db.parent.mkdir(parents=True, exist_ok=True)

    # Enumeration and fingerprinting are INSIDE the abort boundary. If the
    # lesson set cannot be determined (unsearchable directory, I/O fault), we
    # must not proceed: an empty snapshot is indistinguishable from "all
    # lessons deleted" and would replace a good index with an empty one.
    try:
        paths = lesson_paths()
    except OSError as exc:
        print(f"index build aborted: cannot list lessons: {exc}", file=sys.stderr)
        print("nothing was published; the previous index is unchanged", file=sys.stderr)
        return 1
    print(f"found {len(paths)} lessons in {CONFIG.lessons_dir}")

    # Snapshot the source identity BEFORE reading any lesson. If a lesson
    # changes mid-build, the stored fingerprint no longer matches the live one,
    # so the next query treats the index as stale and rebuilds -- rather than
    # serving an embedding that silently no longer matches its source.
    try:
        fingerprint = lesson_fingerprint(paths)
    except OSError as exc:
        print(f"index build aborted: cannot fingerprint lessons: {exc}", file=sys.stderr)
        print("nothing was published; the previous index is unchanged", file=sys.stderr)
        return 1

    try:
        return _build(args, paths, fingerprint)
    except BuildError as exc:
        print(f"index build aborted: {exc}", file=sys.stderr)
        print("nothing was published; the previous index is unchanged", file=sys.stderr)
        return 1


def _build(args, paths: list[Path], fingerprint: str) -> int:
    if args.incremental and CONFIG.index_db.exists():
        compatible, reason = index_is_compatible(CONFIG.index_db)
        if compatible:
            incremental_index(paths, fingerprint)
        else:
            # Never restamp metadata over vectors built under another
            # configuration; a full rebuild is atomic and takes seconds.
            print(f"incremental not possible ({reason}); rebuilding in full")
            full_index(paths, fingerprint)
    else:
        full_index(paths, fingerprint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
