"""Chart grammar.

Charts are declared, not hand-coded, so that every rendered series can carry its
evidence status and every figure can name its sources and methodology. One-off
plotting code cannot make those guarantees.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ChartType(StrEnum):
    CASH_FLOW_WATERFALL = "cash_flow_waterfall"
    CAPITAL_WATERFALL = "capital_waterfall"
    CAPEX_COMPOSITION_TIMELINE = "capex_composition_timeline"
    SPEND_TO_SERVICE_TIMELINE = "spend_to_service_timeline"
    VINTAGE_HEATMAP = "vintage_heatmap"
    ROIC_DECOMPOSITION = "roic_decomposition"
    SENSITIVITY_TORNADO = "sensitivity_tornado"
    KNOWN_VS_INFERRED = "known_vs_inferred"
    REPORTED_VS_ECONOMIC = "reported_vs_economic"


class Annotation(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: str
    text: str
    source_id: str | None = None


class ChartSpec(BaseModel):
    """A renderer-independent chart description.

    Plotly is one consumer; a static site that never runs Python is another.
    """

    model_config = ConfigDict(frozen=True)

    chart_type: ChartType
    title: str
    subtitle: str | None = None

    x_field: str
    y_fields: tuple[str, ...]
    data_ref: str
    """Key into the bundle's data tables, not inline data."""

    value_status_field: str | None = None
    """Column holding each point's :class:`EvidenceStatus`.

    When set, the renderer marks estimated and scenario points differently from
    reported ones. Charts that mix statuses without this field are a bug.
    """

    unit: str | None = None
    source_ids: tuple[str, ...] = ()
    annotations: tuple[Annotation, ...] = ()
    methodology_note: str | None = None
