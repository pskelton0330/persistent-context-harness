#!/usr/bin/env python3
"""Append-only log of what recall did, and how well.

This is the feedback signal the self-improvement loop runs on. Without it there
is no way to answer the questions that actually matter: is recall firing at all,
which lessons never surface, and are we retrieving noise?

PRIVACY: prompt TEXT is never written. Only its length, the working directory,
and which lessons came back. The log is a quality signal, not a transcript —
and a file quietly accumulating everything a user typed would be a liability,
especially since it lives on disk next to a knowledge base.

Stdlib only; used by a hook on the prompt path, so failures are swallowed. A
logging problem must never cost someone their turn.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness_config import CONFIG  # noqa: E402

# Rotated rather than allowed to grow without bound: this is appended to on
# every problem-shaped prompt, forever.
MAX_BYTES = 4 * 1024 * 1024


def _rotate(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.replace(path.with_suffix(".jsonl.1"))
    except OSError:
        pass


def record(
    *,
    cwd: str,
    prompt_len: int,
    retriever: str,
    hits: list[dict],
    fired: bool,
    degraded: bool = False,
) -> None:
    """Record one retrieval attempt. Never raises."""
    try:
        path = CONFIG.retrieval_log
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate(path)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cwd": cwd,
            "prompt_len": prompt_len,   # length only, never the text
            "retriever": retriever,
            "degraded": degraded,       # semantic unavailable, keyword used
            "n_hits": len(hits),
            "fired": fired,             # did we actually inject context
            "hits": hits[:8],
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except (OSError, ValueError, TypeError):
        pass


def read_recent(days: int = 30) -> list[dict]:
    """Entries from the last `days`. Returns [] if the log is unreadable."""
    cutoff = time.time() - days * 86400
    out: list[dict] = []
    for candidate in (CONFIG.retrieval_log, CONFIG.retrieval_log.with_suffix(".jsonl.1")):
        try:
            if not candidate.exists():
                continue
            with candidate.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        entry = json.loads(line)
                        stamp = datetime.fromisoformat(entry["ts"]).timestamp()
                    except (ValueError, KeyError, TypeError):
                        continue
                    if stamp >= cutoff:
                        out.append(entry)
        except OSError:
            continue
    return out


def summarize(days: int = 30) -> dict:
    """Aggregate the signal the weekly review acts on."""
    entries = read_recent(days)
    fired = [e for e in entries if e.get("fired")]
    misses = [e for e in entries if not e.get("fired")]
    degraded = [e for e in entries if e.get("degraded")]

    lesson_hits: dict[str, int] = {}
    for entry in fired:
        for hit in entry.get("hits", []):
            path = hit.get("path")
            if path:
                lesson_hits[path] = lesson_hits.get(path, 0) + 1

    # Lessons that exist but have never been retrieved. Either they are badly
    # written, badly linked, or cover something that never recurs -- all worth
    # knowing, and invisible without this.
    try:
        all_lessons = {str(p) for p in CONFIG.lessons_dir.glob("*.md") if p.is_file()}
    except OSError:
        all_lessons = set()
    retrieved = {Path(p).name for p in lesson_hits}
    never = sorted(p for p in all_lessons if Path(p).name not in retrieved)

    return {
        "days": days,
        "attempts": len(entries),
        "fired": len(fired),
        "misses": len(misses),
        "degraded": len(degraded),
        "hit_rate": round(len(fired) / len(entries), 3) if entries else 0.0,
        "top_lessons": sorted(lesson_hits.items(), key=lambda kv: -kv[1])[:10],
        "never_retrieved": never,
        "lesson_count": len(all_lessons),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Retrieval-log statistics.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    stats = summarize(args.days)
    if args.json:
        print(json.dumps(stats, indent=2))
        raise SystemExit(0)

    print(f"retrieval over the last {stats['days']} days")
    print(f"  attempts      : {stats['attempts']}")
    print(f"  injected      : {stats['fired']}  (hit rate {stats['hit_rate']:.0%})")
    print(f"  no match      : {stats['misses']}")
    if stats["degraded"]:
        print(f"  degraded      : {stats['degraded']}  (semantic unavailable, keyword used)")
    if stats["top_lessons"]:
        print("  most surfaced :")
        for path, count in stats["top_lessons"][:5]:
            print(f"      {count:3d}x  {Path(path).name}")
    never = stats["never_retrieved"]
    if never:
        print(f"  never surfaced: {len(never)}/{stats['lesson_count']} lessons")
        for path in never[:5]:
            print(f"      {Path(path).name}")
        if len(never) > 5:
            print(f"      ... and {len(never) - 5} more")
