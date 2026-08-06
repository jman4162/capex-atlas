"""Chart specifications a bundle carries.

Declared rather than drawn, so the same description feeds the Streamlit lab, a
static README figure and a site that never runs Python. Each spec names the
column carrying evidence status, which is what lets a renderer draw a scenario
differently from a measurement instead of flattening the two.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from capex_atlas.schemas.charts import Annotation, ChartSpec, ChartType
from capex_atlas.schemas.facts import FinancialFact
from capex_atlas.schemas.period import PeriodKind
from capex_atlas.schemas.values import AnalyticalValue

CAPEX_VS_DEPRECIATION = "capex_vs_depreciation"
EVIDENCE_MIX = "evidence_mix"
VINTAGE_CASH_FLOW = "vintage_cash_flow"


def build_specs(
    values: Sequence[AnalyticalValue],
    facts: Sequence[FinancialFact],
    *,
    entity_id: str,
    has_scenario: bool,
) -> tuple[ChartSpec, ...]:
    """The charts this bundle has the data to draw."""
    specs: list[ChartSpec] = [_evidence_mix(entity_id)]
    if _annual_years(facts):
        specs.append(_capex_vs_depreciation(entity_id))
    if has_scenario:
        specs.append(vintage_cash_flow_spec(entity_id))
    return tuple(specs)


def _annual_years(facts: Sequence[FinancialFact]) -> list[str]:
    return sorted(
        {fact.period.label for fact in facts if fact.period.kind is PeriodKind.FISCAL_YEAR}
    )


def _evidence_mix(entity_id: str) -> ChartSpec:
    return ChartSpec(
        chart_type=ChartType.KNOWN_VS_INFERRED,
        title=f"{entity_id}: how much of this analysis is measured",
        subtitle="Every published figure, by how much weight it carries",
        x_field="status",
        y_fields=("count",),
        data_ref=EVIDENCE_MIX,
        value_status_field="status",
        unit="figures",
        methodology_note=(
            "A calculation is never itself reported, however solid its inputs, so nothing "
            "here can sit in the leftmost bar."
        ),
    )


def _capex_vs_depreciation(entity_id: str) -> ChartSpec:
    return ChartSpec(
        chart_type=ChartType.CAPEX_COMPOSITION_TIMELINE,
        title=f"{entity_id}: capital spending against depreciation",
        subtitle="Annual periods only",
        x_field="period",
        y_fields=("capex", "depreciation"),
        data_ref=CAPEX_VS_DEPRECIATION,
        value_status_field="status",
        unit="USD",
        methodology_note=(
            "Cash leaves when capital is bought; depreciation starts when it enters "
            "service. The gap between the two lines is that lag."
        ),
    )


def vintage_cash_flow_spec(entity_id: str) -> ChartSpec:
    return ChartSpec(
        chart_type=ChartType.SPEND_TO_SERVICE_TIMELINE,
        title=f"{entity_id}: modelled cash profile of one capital vintage",
        subtitle="Illustrative assumptions, not an estimate of any company's returns",
        x_field="year",
        y_fields=("free_cash_flow",),
        data_ref=VINTAGE_CASH_FLOW,
        value_status_field="status",
        unit="USD",
        annotations=(Annotation(x="0", text="capital committed"),),
        methodology_note="Every point is a scenario; nothing here is measured.",
    )


def chart_data(
    spec: ChartSpec,
    *,
    values: Sequence[AnalyticalValue],
    facts: Sequence[FinancialFact],
    scenario: Any | None = None,
) -> dict[str, list[Any]]:
    """Assemble the columns *spec* names, from the bundle's own contents."""
    if spec.data_ref == EVIDENCE_MIX:
        counts: dict[str, int] = {}
        for value in values:
            counts[value.status.value] = counts.get(value.status.value, 0) + 1
        ordered = sorted(counts, key=lambda name: _status_rank(name))
        return {
            "status": ordered,
            "count": [counts[name] for name in ordered],
        }

    if spec.data_ref == CAPEX_VS_DEPRECIATION:
        years = _annual_years(facts)
        by_year: dict[str, dict[str, Any]] = {year: {} for year in years}
        for fact in facts:
            if fact.period.kind is not PeriodKind.FISCAL_YEAR:
                continue
            if "PaymentsToAcquireProperty" in fact.metric_id:
                by_year[fact.period.label]["capex"] = fact.value
            elif fact.metric_id.startswith("Depreciation"):
                by_year[fact.period.label].setdefault("depreciation", fact.value)
        usable = [year for year in years if "capex" in by_year[year]]
        return {
            "period": usable,
            "capex": [by_year[year].get("capex") for year in usable],
            "depreciation": [by_year[year].get("depreciation") for year in usable],
            "status": ["reported"] * len(usable),
        }

    if spec.data_ref == VINTAGE_CASH_FLOW and scenario is not None:
        years = [row.year for row in scenario.schedule.years]
        return {
            "year": [str(year) for year in years],
            "free_cash_flow": [row.free_cash_flow for row in scenario.schedule.years],
            "status": ["scenario"] * len(years),
        }

    return {}


def _status_rank(name: str) -> int:
    from capex_atlas.schemas.evidence import EvidenceStatus

    return EvidenceStatus(name).rank
