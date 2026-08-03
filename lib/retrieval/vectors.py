#!/usr/bin/env python3
"""Embedding-vector validation and packing, shared by the indexer and retriever.

There is exactly one validator so the write path and the query path cannot
disagree about what counts as a usable vector. A vector that is good enough to
store must be good enough to query with, and vice versa.

Stdlib only: the retriever must be able to import this even when the optional
extras (`requests`, `sqlite-vec`) are absent.
"""

from __future__ import annotations

import math
import struct

# sqlite-vec stores float32. Values outside its range cannot be packed, and
# struct.pack raises OverflowError -- which, uncaught on a prompt hook, would
# crash the user's turn instead of degrading to keyword recall.
FLOAT32_MAX = 3.4028235e38


class VectorError(ValueError):
    """A vector is unusable. Callers must degrade, never propagate this."""


def validate_vector(vector: object, expected_dim: int, label: str = "vector") -> list[float]:
    """Return the vector if usable, else raise VectorError."""
    if not isinstance(vector, list):
        raise VectorError(f"{label} is {type(vector).__name__}, not a list")
    if len(vector) != expected_dim:
        raise VectorError(
            f"{label} has dimension {len(vector)}, expected {expected_dim} "
            "(is KB_EMBED_DIM correct for this model?)"
        )
    for value in vector:
        # bool is a subclass of int; a boolean here means the backend returned
        # something structurally wrong, so reject it rather than coerce.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VectorError(f"{label} contains a non-numeric value")
        # Every numeric check runs inside the guard. JSON permits unbounded
        # integers, and math.isfinite(10**400) raises OverflowError before any
        # range test would run -- which previously escaped as an uncaught
        # exception and could crash a hook on the user's prompt.
        try:
            if not math.isfinite(value):
                raise VectorError(f"{label} contains NaN or infinity")
            if abs(value) > FLOAT32_MAX:
                raise VectorError(f"{label} contains a value outside float32 range")
        except VectorError:
            raise
        except (OverflowError, TypeError, ValueError) as exc:
            raise VectorError(f"{label} contains an unusable number: {exc}") from exc
    return vector


def validate_batch(vectors: object, expected_count: int, expected_dim: int) -> list[list[float]]:
    """Validate a whole embedding response.

    Cardinality is checked first: a backend returning 15 vectors for 16 inputs
    would otherwise be silently truncated by zip(), dropping a lesson from the
    index while metadata still advanced.
    """
    if not isinstance(vectors, list):
        raise VectorError(f"expected a list of vectors, got {type(vectors).__name__}")
    if len(vectors) != expected_count:
        raise VectorError(f"backend returned {len(vectors)} vectors for {expected_count} inputs")
    for index, vector in enumerate(vectors):
        validate_vector(vector, expected_dim, f"vector {index}")
    return vectors  # type: ignore[return-value]


def floats_to_bytes(vector: list[float]) -> bytes:
    """Pack to the float32 blob sqlite-vec expects.

    Any packing failure is normalized to VectorError so callers need only catch
    one exception type.
    """
    try:
        return struct.pack(f"{len(vector)}f", *vector)
    except (struct.error, OverflowError, TypeError, ValueError) as exc:
        raise VectorError(f"cannot pack vector: {exc}") from exc
