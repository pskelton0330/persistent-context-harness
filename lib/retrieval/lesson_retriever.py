#!/usr/bin/env python3
"""Semantic search over the lesson index.

Reads a prompt from argv or stdin, embeds it, runs vector kNN against the
sqlite-vec index, and prints matching lessons for an agent to read before it
starts debugging.

Exit codes are the contract with the calling hook:
    0  — ran successfully (zero matches is success; it prints nothing)
    2  — semantic search unavailable (backend down, index missing, or index
         built with a different embedding model) — caller should fall back to
         keyword recall rather than losing recall entirely

Fast path: ~50-100 ms when the embedding backend is warm.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_config import CONFIG  # noqa: E402
from indexmeta import (  # noqa: E402
    SCHEMA_VERSION,
    current_fingerprint,
    rowid_integrity,
)
from vectors import VectorError, floats_to_bytes, validate_vector  # noqa: E402

try:
    import requests
    import sqlite_vec
except ImportError:
    # Extras absent is a normal, supported configuration: the caller falls back
    # to keyword recall. Never crash the user's prompt over it.
    sys.exit(2)

# Cosine distance above this is noise. Tuned to keep unrelated lessons out --
# the false-positive problem that motivated semantic search in the first place.
DEFAULT_MAX_DISTANCE = 0.85
DEFAULT_TOP_K = 4

def embed(text: str) -> list[float] | None:
    try:
        response = requests.post(
            CONFIG.embed_url,
            json={"model": CONFIG.embed_model, "input": text},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]
    except Exception:
        return None


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{CONFIG.index_db}?mode=ro", uri=True)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    return conn


def read_meta(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        return {key: value for key, value in conn.execute("SELECT key, value FROM meta")}
    except sqlite3.Error:
        return {}


def index_health(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Is this index safe to query for the ACTIVE configuration?

    Every "no" here must reach the caller as exit 2 so it falls back to keyword
    recall. The failure mode this exists to prevent is subtle: an unhealthy
    index does not error, it just returns zero (or wrong) neighbours, which
    looks exactly like "no relevant lessons" and silently loses recall.
    """
    meta = read_meta(conn)

    # Missing metadata is not trusted. Vectors of unknown provenance are not
    # comparable to prompt vectors from the current model.
    for key in ("schema_version", "embed_model", "embed_dim", "kb_root", "lesson_fingerprint"):
        if not meta.get(key):
            return False, f"index metadata missing {key}; rebuild with `kb index`"

    if meta["schema_version"] != str(SCHEMA_VERSION):
        return False, f"index schema {meta['schema_version']} != expected {SCHEMA_VERSION}"
    if meta["embed_model"] != CONFIG.embed_model:
        return False, f"index built with model {meta['embed_model']!r}, config says {CONFIG.embed_model!r}"
    if meta["embed_dim"] != str(CONFIG.embed_dim):
        return False, f"index dimension {meta['embed_dim']} != configured {CONFIG.embed_dim}"
    if meta["kb_root"] != str(CONFIG.kb_root):
        # Reusing a state dir across two KBs would return KB-A vectors while
        # formatting their relative paths under KB-B.
        return False, f"index built against a different KB ({meta['kb_root']})"

    integral, reason = rowid_integrity(conn)
    if not integral:
        return False, reason

    # Exact content identity, not a wall-clock comparison: mtime-vs-timestamp
    # was racy in both directions (a lesson edited mid-build looked fresh; a
    # sub-second rebuild looked stale).
    if meta["lesson_fingerprint"] != current_fingerprint():
        return False, "index is stale; lessons changed since it was built"

    return True, "healthy"


def search(embedding: list[float], k: int) -> list[tuple[str, str, float]]:
    conn = open_db()
    try:
        healthy, reason = index_health(conn)
        if not healthy:
            raise RuntimeError(reason)
        rows = conn.execute(
            """
            SELECT l.path, l.title, v.distance
            FROM vec_lessons v
            JOIN lessons l ON v.rowid = l.id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (floats_to_bytes(embedding), k),
        ).fetchall()
        return [(path, title, distance) for path, title, distance in rows]
    finally:
        conn.close()


def format_output(hits: list[tuple[str, str, float]]) -> str:
    if not hits:
        return ""
    lines = [
        "[lesson-recall] This message reads like a problem report. The lessons "
        "below were retrieved by semantic similarity to the described symptom — "
        "READ THEM BEFORE debugging from scratch. Check whether the current "
        "symptom matches their Root cause, and apply their Prevention steps. If "
        "one clearly applies, say so explicitly and short-circuit to the fix.",
        "",
    ]
    for path, title, distance in hits:
        # Lower distance = closer match; show it as a readable relevance figure.
        relevance = max(0, int((1.0 - distance) * 100))
        absolute = CONFIG.kb_root / path if not Path(path).is_absolute() else Path(path)
        lines.append(f"- {absolute}  [relevance={relevance}%, distance={distance:.3f}]")
        if title:
            lines.append(f"  TITLE: {title}")
    lines += [
        "",
        "If none of these actually apply, continue normal debugging — but say "
        "briefly why they don't fit, so the reasoning is visible.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic lesson recall.")
    parser.add_argument("prompt", nargs="?", help="prompt text (default: stdin)")
    parser.add_argument("-k", "--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--max-distance",
        type=float,
        default=DEFAULT_MAX_DISTANCE,
        help=f"drop hits above this cosine distance (default {DEFAULT_MAX_DISTANCE})",
    )
    parser.add_argument("--json", action="store_true", help="emit agent hook JSON")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report index health and exit (no query)",
    )
    args = parser.parse_args()

    if not CONFIG.index_db.exists():
        if args.check:
            print(f"index missing: {CONFIG.index_db}")
        return 2

    if args.check:
        try:
            conn = open_db()
        except sqlite3.Error as exc:
            print(f"index unreadable: {exc}")
            return 2
        try:
            meta = read_meta(conn)
            count = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
            healthy, reason = index_health(conn)
        except sqlite3.Error as exc:
            print(f"index unreadable: {exc}")
            return 2
        finally:
            conn.close()
        print(f"index:   {CONFIG.index_db}")
        print(f"lessons: {count}")
        print(f"model:   {meta.get('embed_model', '(unknown)')} dim={meta.get('embed_dim', '?')}")
        print(f"kb_root: {meta.get('kb_root', '(unknown)')}")
        print(f"healthy: {healthy} ({reason})")
        return 0 if healthy else 2

    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    prompt = prompt.strip()
    if not prompt:
        return 0

    embedding = embed(prompt)
    if embedding is None:
        return 2  # backend unreachable — caller falls back to keyword

    # Validate with the SAME checker the indexer uses, so a vector that would be
    # rejected on write is also rejected on query. A malformed vector must
    # degrade to keyword recall, never raise inside a hook on the user's prompt.
    try:
        validate_vector(embedding, CONFIG.embed_dim, "prompt embedding")
    except VectorError:
        return 2

    try:
        hits = [hit for hit in search(embedding, args.top_k) if hit[2] <= args.max_distance]
    # VectorError covers packing failures (including OverflowError on values
    # outside float32 range), which floats_to_bytes normalizes for us.
    except (sqlite3.Error, RuntimeError, VectorError, ValueError, TypeError):
        return 2

    output = format_output(hits)
    if not output:
        return 0

    if args.json:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": output,
                    }
                }
            )
        )
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
