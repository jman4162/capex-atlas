"""Deterministic identifiers.

Every id in Capex Atlas is a function of content, never of wall-clock time or
insertion order. Re-running the same analysis over the same inputs must produce
the same ids, or bundle diffing and reproducibility checks are meaningless.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from decimal import Decimal

_DIGEST_BYTES = 8
_SEPARATOR = b"\x1f"


def stable_id(prefix: str, *parts: object) -> str:
    """Return ``<prefix>:<16 hex chars>`` derived from *parts*.

    Ordering of mappings and sets is normalized so that logically identical
    inputs hash identically regardless of construction order.
    """
    digest = hashlib.blake2b(digest_size=_DIGEST_BYTES)
    for part in parts:
        digest.update(canonical(part).encode("utf-8"))
        digest.update(_SEPARATOR)
    return f"{prefix}:{digest.hexdigest()}"


def canonical(value: object) -> str:
    """Render *value* as a stable string for hashing."""
    if value is None:
        return "\x00none"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        # Normalize so 1.50 and 1.5 hash alike; keep the sign of zero out of it.
        normalized = value.normalize()
        return f"{normalized:f}"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, Mapping):
        items = sorted((canonical(k), canonical(v)) for k, v in value.items())
        return "{" + ",".join(f"{k}={v}" for k, v in items) + "}"
    if isinstance(value, frozenset | set):
        return "{" + ",".join(sorted(canonical(v) for v in value)) + "}"
    if isinstance(value, Sequence):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    return repr(value)
