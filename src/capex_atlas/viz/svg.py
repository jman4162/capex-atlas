"""Static SVG rendering, with no plotting dependency.

Plotly's own image export needs Kaleido, which ships a browser and whose output
shifts between versions. Neither is acceptable here: the figures are committed
and CI fails on drift, so the writer has to be byte-deterministic, and the core
package should not need a browser to draw a bar chart.

So this renders the same figure dictionaries the Plotly path produces, in a few
hundred bytes of geometry. It covers the chart shapes this package actually
emits and refuses anything else rather than guessing.

Evidence status survives the trip. Scenario bars are hatched and faded exactly
as they are in the app, because a static figure that flattens a what-if into a
measurement is the same failure in a different medium.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

WIDTH = 900
HEIGHT = 460
MARGIN_LEFT = 96
MARGIN_RIGHT = 28
MARGIN_TOP = 78
MARGIN_BOTTOM = 118

SERIES_COLOURS = ("#2f5d8a", "#c2724a", "#5b8c5a", "#8a6ba8")
AXIS = "#333333"
GRID = "#e3e3e3"
MUTED = "#666666"

STATUS_OPACITY = {
    "reported": 1.0,
    "derived": 0.92,
    "estimated": 0.72,
    "scenario": 0.55,
    "unresolved": 0.3,
}
STATUS_HATCH = {"estimated": "hatch-estimated", "scenario": "hatch-scenario"}


class UnsupportedFigureError(ValueError):
    """This writer covers the shapes the package emits, and says so otherwise."""


def render_svg(figure: dict[str, Any]) -> str:
    """Turn a Plotly figure dictionary into a deterministic SVG document."""
    traces = [trace for trace in figure.get("data", []) if trace.get("y")]
    if not traces:
        raise UnsupportedFigureError("figure has no plottable series")
    for trace in traces:
        if trace.get("type") not in {"bar", "scatter"}:
            raise UnsupportedFigureError(f"unsupported trace type {trace.get('type')!r}")

    layout = figure.get("layout", {})
    labels = [str(item) for item in traces[0]["x"]]
    statuses = [str(item) for item in traces[0].get("customdata", [])]
    if len(statuses) != len(labels):
        statuses = ["derived"] * len(labels)

    numbers = [value for trace in traces for value in trace["y"] if value is not None]
    if not numbers:
        raise UnsupportedFigureError("every point is empty")
    top = max(max(numbers), 0.0)
    bottom = min(min(numbers), 0.0)
    if top == bottom:
        top = bottom + 1.0

    plot_width = WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    plot_height = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

    def y_of(value: float) -> float:
        share = (float(value) - bottom) / (top - bottom)
        return float(MARGIN_TOP + plot_height - share * plot_height)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="Helvetica, Arial, sans-serif">',
        _defs(),
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>',
    ]
    parts.extend(_title(layout))
    parts.extend(_gridlines(bottom, top, y_of))
    parts.extend(_bars(traces, labels, statuses, plot_width, y_of, bottom))
    parts.extend(_x_labels(labels, plot_width))
    parts.extend(_legend(traces))
    parts.extend(_footer(layout))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _defs() -> str:
    """Hatch patterns, so status is readable without relying on colour."""
    return (
        "<defs>"
        '<pattern id="hatch-estimated" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="6" stroke="#ffffff" stroke-width="2.4"/></pattern>'
        '<pattern id="hatch-scenario" width="7" height="7" patternUnits="userSpaceOnUse">'
        '<path d="M0,0 l7,7 M7,0 l-7,7" stroke="#ffffff" stroke-width="1.6"/></pattern>'
        "</defs>"
    )


def _title(layout: dict[str, Any]) -> list[str]:
    title = layout.get("title", {})
    text = str(title.get("text", ""))
    subtitle = str(title.get("subtitle", {}).get("text", "")) if title.get("subtitle") else ""
    out = [
        f'<text x="{MARGIN_LEFT}" y="34" font-size="19" fill="{AXIS}" '
        f'font-weight="600">{escape(text)}</text>'
    ]
    if subtitle:
        out.append(
            f'<text x="{MARGIN_LEFT}" y="56" font-size="13" fill="{MUTED}">'
            f"{escape(subtitle)}</text>"
        )
    return out


def _gridlines(bottom: float, top: float, y_of: Any) -> list[str]:
    out: list[str] = []
    for step in range(5):
        value = bottom + (top - bottom) * step / 4
        y = y_of(value)
        out.append(
            f'<line x1="{MARGIN_LEFT}" y1="{y:.1f}" x2="{WIDTH - MARGIN_RIGHT}" '
            f'y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{MARGIN_LEFT - 10}" y="{y + 4:.1f}" font-size="11" fill="{MUTED}" '
            f'text-anchor="end">{_compact(value)}</text>'
        )
    zero = y_of(0.0)
    out.append(
        f'<line x1="{MARGIN_LEFT}" y1="{zero:.1f}" x2="{WIDTH - MARGIN_RIGHT}" '
        f'y2="{zero:.1f}" stroke="{AXIS}" stroke-width="1.4"/>'
    )
    return out


def _bars(
    traces: list[dict[str, Any]],
    labels: list[str],
    statuses: list[str],
    plot_width: float,
    y_of: Any,
    bottom: float,
) -> list[str]:
    out: list[str] = []
    slot = plot_width / max(len(labels), 1)
    series_count = len(traces)
    bar_width = min(slot * 0.72 / series_count, 74.0)
    zero = y_of(0.0)

    for series_index, trace in enumerate(traces):
        colour = SERIES_COLOURS[series_index % len(SERIES_COLOURS)]
        for point_index, value in enumerate(trace["y"]):
            if value is None:
                continue
            group_left = MARGIN_LEFT + slot * point_index + (slot - bar_width * series_count) / 2
            x = group_left + bar_width * series_index
            y = y_of(float(value))
            height = abs(y - zero)
            status = statuses[point_index] if point_index < len(statuses) else "derived"
            opacity = STATUS_OPACITY.get(status, 0.9)
            out.append(
                f'<rect x="{x:.1f}" y="{min(y, zero):.1f}" width="{bar_width:.1f}" '
                f'height="{max(height, 1.0):.1f}" fill="{colour}" opacity="{opacity:.2f}"/>'
            )
            hatch = STATUS_HATCH.get(status)
            if hatch:
                out.append(
                    f'<rect x="{x:.1f}" y="{min(y, zero):.1f}" width="{bar_width:.1f}" '
                    f'height="{max(height, 1.0):.1f}" fill="url(#{hatch})" opacity="0.85"/>'
                )
    return out


def _x_labels(labels: list[str], plot_width: float) -> list[str]:
    slot = plot_width / max(len(labels), 1)
    baseline = HEIGHT - MARGIN_BOTTOM + 20
    return [
        f'<text x="{MARGIN_LEFT + slot * index + slot / 2:.1f}" y="{baseline}" '
        f'font-size="12" fill="{AXIS}" text-anchor="middle">{escape(label)}</text>'
        for index, label in enumerate(labels)
    ]


def _legend(traces: list[dict[str, Any]]) -> list[str]:
    if len(traces) < 2:
        return []
    out: list[str] = []
    x = MARGIN_LEFT
    y = HEIGHT - MARGIN_BOTTOM + 44
    for index, trace in enumerate(traces):
        colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
        out.append(f'<rect x="{x}" y="{y - 9}" width="11" height="11" fill="{colour}"/>')
        name = str(trace.get("name", ""))
        out.append(f'<text x="{x + 17}" y="{y}" font-size="12" fill="{AXIS}">{escape(name)}</text>')
        x += 22 + 7 * len(name)
    return out


def _footer(layout: dict[str, Any]) -> list[str]:
    annotations = layout.get("annotations", [])
    if not annotations:
        return []
    text = str(annotations[0].get("text", ""))
    out: list[str] = []
    for offset, line in enumerate(_wrap(text, 118)):
        out.append(
            f'<text x="{MARGIN_LEFT}" y="{HEIGHT - 40 + offset * 14}" font-size="10.5" '
            f'fill="{MUTED}">{escape(line)}</text>'
        )
    return out


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def _compact(value: float) -> str:
    """Axis labels a reader can take in, without implying false precision."""
    magnitude = abs(value)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if magnitude >= limit:
            return f"{value / limit:.1f}{suffix}"
    if magnitude < 1 and magnitude > 0:
        return f"{Decimal(str(round(value, 3))).normalize():f}"
    return f"{value:.0f}"
