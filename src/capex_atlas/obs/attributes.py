"""What is allowed onto a span.

Metadata only, enforced rather than requested. Traces are the easiest place for
filing text, a model prompt or a user's own data to leak into an exporter nobody
audits, and the leak is invisible until someone reads the backend.

So the policy is a function with tests: identifiers, counts, hashes and statuses
pass; anything that looks like content is rejected at the call site, where the
author can see it. Rejecting beats truncating, because a truncated prompt is
still a prompt.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from decimal import Decimal
from typing import Final

NAMESPACE: Final = "capex_atlas."

MAX_VALUE_CHARS: Final = 120
"""Longest permitted string value.

Comfortably fits an accession number, a period label or a metric id, and
comfortably fails a sentence of a filing.
"""

CONTENT_BEARING: Final = frozenset(
    {
        "body",
        "content",
        "document",
        "excerpt",
        "filing",
        "message",
        "passage",
        "prompt",
        "quote",
        "reasoning",
        "response",
        "snippet",
        "text",
        "transcript",
    }
)
"""Key fragments that indicate the value is content rather than metadata.

Matched against the dotted segments of an attribute name, so
``capex_atlas.claim.quote`` is refused while ``capex_atlas.claim.quote_sha256``
is allowed: a hash identifies a passage without reproducing it.
"""

AttributeValue = str | int | float | bool


class AttributePolicyError(ValueError):
    """An attribute would have put content, or something unbounded, on a span."""


def content_digest(text: str) -> str:
    """A short hash standing in for a passage that must not be traced.

    Lets a trace say "this is the same text as before" without carrying the text.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def sanitize(attributes: Mapping[str, object]) -> dict[str, AttributeValue]:
    """Validate and normalize span attributes, or raise.

    Raising rather than dropping is deliberate. A silently discarded attribute
    teaches nobody; a failure at the call site gets the policy learned once.
    """
    clean: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        _check_key(key)
        clean[key] = _check_value(key, value)
    return clean


def _check_key(key: str) -> None:
    if not key.startswith(NAMESPACE):
        raise AttributePolicyError(
            f"attribute {key!r} must start with {NAMESPACE!r} so this package's own "
            "attributes stay distinguishable from evolving semantic conventions"
        )
    segments = key.removeprefix(NAMESPACE).split(".")
    offending = [segment for segment in segments if segment in CONTENT_BEARING]
    if offending:
        raise AttributePolicyError(
            f"attribute {key!r} names {offending[0]!r}, which carries content rather than "
            "metadata. Trace an id, a count or content_digest(text) instead."
        )


def _check_value(key: str, value: object) -> AttributeValue:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, Decimal):
        raise AttributePolicyError(
            f"attribute {key!r} is a Decimal. Financial values belong in the calculation "
            "graph, not on a span, where they would be high-cardinality and lossy."
        )
    if not isinstance(value, str):
        raise AttributePolicyError(
            f"attribute {key!r} is {type(value).__name__}; spans take scalars only"
        )
    if len(value) > MAX_VALUE_CHARS:
        raise AttributePolicyError(
            f"attribute {key!r} is {len(value)} characters, over the {MAX_VALUE_CHARS} "
            "limit. A value this long is probably document text; hash it with "
            "content_digest() if the trace needs to identify it."
        )
    return value
