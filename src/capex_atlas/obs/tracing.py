"""Tracing.

OpenTelemetry is optional. Without it installed every span here is a no-op, so
the deterministic core keeps working and instrumentation can be sprinkled through
the library without forcing a dependency on anyone who only wanted the metrics.

One provider, configured once by the application. Letting each component build
its own gives duplicate exporters, inconsistent resources and traces that do not
join up.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Final

from capex_atlas.obs.attributes import AttributeValue, sanitize

SERVICE_NAME: Final = "capex-atlas"

SPAN_NAMES: Final = (
    "capex_atlas.source.download",
    "capex_atlas.document.parse",
    "capex_atlas.fact.extract",
    "capex_atlas.reconciliation.run",
    "capex_atlas.metric.calculate",
    "capex_atlas.scenario.run",
    "capex_atlas.claim.verify",
    "capex_atlas.review.approve",
    "capex_atlas.bundle.publish",
    "capex_atlas.ui.interaction",
)
"""The span taxonomy. Adding a name here first keeps the vocabulary stable."""

_configured = False


def available() -> bool:
    """Whether the OpenTelemetry SDK is importable."""
    try:
        import opentelemetry.trace  # noqa: F401
    except ImportError:
        return False
    return True


def configure(*, service_name: str = SERVICE_NAME, force: bool = False) -> bool:
    """Set up the global tracer provider once. Returns whether tracing is live.

    Safe to call when OpenTelemetry is absent; it simply reports ``False``.
    """
    global _configured
    if _configured and not force:
        return available()
    if not available():
        return False

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    trace.set_tracer_provider(provider)
    _configured = True
    return True


@contextmanager
def span(name: str, **attributes: object) -> Iterator[Any]:
    """Open a span, with attributes checked against the metadata-only policy.

    The policy runs whether or not OpenTelemetry is installed, so a violation
    surfaces in development and in CI rather than only in production where the
    exporter is real.
    """
    checked: dict[str, AttributeValue] = sanitize(attributes)
    if not available():
        yield None
        return

    from opentelemetry import trace

    tracer = trace.get_tracer("capex_atlas")
    with tracer.start_as_current_span(name) as active:
        for key, value in checked.items():
            active.set_attribute(key, value)
        yield active


def annotate(active: Any, attributes: Mapping[str, object]) -> None:
    """Add attributes to an open span, subject to the same policy."""
    if active is None:
        return
    for key, value in sanitize(attributes).items():
        active.set_attribute(key, value)


def current_trace_id() -> str | None:
    """Hex trace id of the active span, for linking a bundle to its run."""
    if not available():
        return None
    from opentelemetry import trace

    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")
