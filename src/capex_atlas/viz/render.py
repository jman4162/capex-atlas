"""Turning a ChartSpec into a figure.

Output is a plain Plotly figure dictionary rather than a Plotly object, so the
core package needs no plotting dependency and a static site can consume the same
JSON without running Python.

The rule that matters here: a mark inherits the evidence status of the value it
draws. A chart that renders a scenario the same way it renders a reported figure
has undone the work every layer beneath it did, so mixed-status series are
styled apart and the legend says which is which.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from capex_atlas.disclaimer import SHORT
from capex_atlas.schemas.charts import ChartSpec, ChartType
from capex_atlas.schemas.evidence import EvidenceStatus

STATUS_PATTERN: dict[EvidenceStatus, str] = {
    EvidenceStatus.REPORTED: "",
    EvidenceStatus.DERIVED: "",
    EvidenceStatus.ESTIMATED: "/",
    EvidenceStatus.SCENARIO: "x",
    EvidenceStatus.UNRESOLVED: ".",
}
"""Hatching by status.

Deliberately not colour alone: a reader who cannot distinguish the palette still
needs to see which bars are measured and which are assumed.
"""

STATUS_OPACITY: dict[EvidenceStatus, float] = {
    EvidenceStatus.REPORTED: 1.0,
    EvidenceStatus.DERIVED: 0.92,
    EvidenceStatus.ESTIMATED: 0.72,
    EvidenceStatus.SCENARIO: 0.55,
    EvidenceStatus.UNRESOLVED: 0.3,
}


class ChartDataError(ValueError):
    pass


def render(spec: ChartSpec, data: dict[str, list[Any]]) -> dict[str, Any]:
    """Build a Plotly figure dictionary for *spec* over *data*.

    *data* maps field names to columns, including the status column when the
    spec names one.
    """
    _validate(spec, data)
    x_values = data[spec.x_field]
    statuses = _statuses(spec, data, len(x_values))

    traces = [
        _trace(spec, name=field, x=x_values, y=data[field], statuses=statuses)
        for field in spec.y_fields
    ]
    return {
        "data": traces,
        "layout": _layout(spec, statuses),
    }


def _validate(spec: ChartSpec, data: dict[str, list[Any]]) -> None:
    if spec.x_field not in data:
        raise ChartDataError(f"{spec.title}: no column {spec.x_field!r}")
    missing = [field for field in spec.y_fields if field not in data]
    if missing:
        raise ChartDataError(f"{spec.title}: missing columns {missing}")
    length = len(data[spec.x_field])
    for field in spec.y_fields:
        if len(data[field]) != length:
            raise ChartDataError(
                f"{spec.title}: column {field!r} has {len(data[field])} points against "
                f"{length} on the x axis"
            )


def _statuses(spec: ChartSpec, data: dict[str, list[Any]], length: int) -> list[EvidenceStatus]:
    if spec.value_status_field is None:
        # No status column, so nothing may claim to be reported. Derived is the
        # weakest safe assumption for a chart built from the fact table.
        return [EvidenceStatus.DERIVED] * length
    column = data.get(spec.value_status_field)
    if column is None:
        raise ChartDataError(f"{spec.title}: no status column {spec.value_status_field!r}")
    return [EvidenceStatus(item) for item in column]


def _trace(
    spec: ChartSpec,
    *,
    name: str,
    x: list[Any],
    y: list[Any],
    statuses: list[EvidenceStatus],
) -> dict[str, Any]:
    numbers = [None if item is None else float(_as_decimal(item)) for item in y]
    mode = _mode_for(spec.chart_type)
    trace: dict[str, Any] = {
        "type": mode,
        "name": name,
        "x": list(x),
        "y": numbers,
        "customdata": [status.value for status in statuses],
        "hovertemplate": (
            f"<b>{name}</b><br>%{{x}}<br>%{{y:,.4g}}"
            f"{' ' + spec.unit if spec.unit else ''}<br>status: %{{customdata}}<extra></extra>"
        ),
    }
    if mode == "bar":
        trace["marker"] = {
            "pattern": {"shape": [STATUS_PATTERN[s] for s in statuses]},
            "opacity": [STATUS_OPACITY[s] for s in statuses],
        }
    else:
        trace["opacity"] = min(STATUS_OPACITY[s] for s in statuses) if statuses else 1.0
    if spec.chart_type is ChartType.CASH_FLOW_WATERFALL:
        trace["type"] = "waterfall"
        trace.pop("marker", None)
    return trace


def _mode_for(chart_type: ChartType) -> str:
    if chart_type in (
        ChartType.CAPEX_COMPOSITION_TIMELINE,
        ChartType.SPEND_TO_SERVICE_TIMELINE,
    ):
        return "scatter"
    if chart_type is ChartType.VINTAGE_HEATMAP:
        return "heatmap"
    return "bar"


def _layout(spec: ChartSpec, statuses: list[EvidenceStatus]) -> dict[str, Any]:
    present = sorted(set(statuses), key=lambda s: s.rank)
    legend = " ".join(f"{status.glyph} {status.value}" for status in present)
    footer_parts = [legend, SHORT]
    if spec.methodology_note:
        footer_parts.insert(1, spec.methodology_note)

    return {
        "title": {"text": spec.title, "subtitle": {"text": spec.subtitle or ""}},
        "yaxis": {"title": {"text": spec.unit or ""}},
        "annotations": [
            {
                "text": " | ".join(part for part in footer_parts if part),
                "showarrow": False,
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.22,
                "align": "left",
                "font": {"size": 10},
            },
            *[
                {
                    "text": item.text,
                    "x": item.x,
                    "showarrow": True,
                    "yref": "paper",
                    "y": 1,
                }
                for item in spec.annotations
            ],
        ],
        "template": "plotly_white",
    }


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
