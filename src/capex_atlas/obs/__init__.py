"""Observability.

OpenTelemetry is optional; without it every span is a no-op. The attribute policy
runs either way, so a violation is caught in CI rather than discovered in an
exporter nobody reads.
"""

from capex_atlas.obs.attributes import (
    AttributePolicyError,
    content_digest,
    sanitize,
)
from capex_atlas.obs.tracing import annotate, available, configure, current_trace_id, span

__all__ = [
    "AttributePolicyError",
    "annotate",
    "available",
    "configure",
    "content_digest",
    "current_trace_id",
    "sanitize",
    "span",
]
