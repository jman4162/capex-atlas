"""Assembling a bundle from a filer's facts.

The pipeline in one place: extract, reconcile, compute, collect. Everything it
publishes is captured with the graph that produced it, so the audit can walk back
from any figure to the filing underneath.

Metrics whose inputs the filer did not tag come out unresolved and are kept
rather than dropped. A reader learning that standardized free cash flow cannot be
computed for this company has learned something; silently omitting the row would
have taught them nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from capex_atlas import __version__
from capex_atlas.accounting.reconciliation import reconcile
from capex_atlas.adapters import adapter_for
from capex_atlas.adapters.base import concrete_concepts, resolve_value_series
from capex_atlas.assumptions.models import Assumption
from capex_atlas.assumptions.registry import AssumptionRegistry
from capex_atlas.bundle.charts import build_specs
from capex_atlas.bundle.model import AnalysisBundle, BundleProvenance
from capex_atlas.metrics import (
    capex_intensity,
    capex_to_depreciation,
    invested_capital_ex_cash,
    invested_capital_operating,
    lease_adjusted_fcf,
    net_investment,
    nopat,
    reported_fcf,
    roic,
    standardized_fcf,
)
from capex_atlas.provenance.graph import calculation_graph
from capex_atlas.scenarios.model import ScenarioResult
from capex_atlas.schemas.facts import FinancialFact
from capex_atlas.schemas.period import PeriodKind
from capex_atlas.schemas.source import SourceReference
from capex_atlas.schemas.values import AnalyticalValue
from capex_atlas.xbrl.companyfacts import extract_facts

TAX_ASSUMPTION = "tax.us_federal_statutory_rate"


class FactScope(StrEnum):
    """How much of a filer's history a bundle carries.

    The trade-off is real. History lets a chart be drawn without re-extracting,
    and it is most of a bundle's bytes. ``used`` keeps only what the published
    figures rest on, which is the right choice for an artifact meant to travel.
    """

    USED = "used"
    """Only the facts the published values were computed from."""

    PERIOD = "period"
    """The analyzed period and its balance-sheet date."""

    ALL = "all"
    """Everything extracted, so charts have a history to draw."""


def _select_facts(
    facts: Sequence[FinancialFact],
    values: Sequence[AnalyticalValue],
    *,
    scope: FactScope,
    period_label: str,
    balance_label: str | None,
) -> tuple[FinancialFact, ...]:
    if scope is FactScope.ALL:
        keep = list(facts)
    elif scope is FactScope.PERIOD:
        wanted = {period_label, balance_label}
        keep = [fact for fact in facts if fact.period.label in wanted]
    else:
        # Each fact now carries its own citation, so the source ids a value
        # names identify exactly the facts it used.
        cited = {source_id for value in values for source_id in value.source_ids}
        keep = [fact for fact in facts if fact.source.source_id in cited]
    return tuple(sorted(keep, key=lambda f: (f.metric_id, f.period.label)))


def build_analysis(
    payload: dict[str, Any],
    *,
    entity_id: str,
    period_label: str,
    source: SourceReference,
    registry: AssumptionRegistry | None = None,
    template: str = "capital-deployment",
    command: str | None = None,
    facts_scope: FactScope = FactScope.ALL,
    scenarios: Sequence[ScenarioResult] = (),
) -> AnalysisBundle:
    """Turn a Company Facts payload into a frozen analysis for one period."""
    adapter = adapter_for(entity_id)

    registry = registry or AssumptionRegistry.load()
    extraction = extract_facts(
        payload,
        entity_id=entity_id,
        calendar=adapter.calendar(),
        source=source,
        statement_map=adapter.statement_map(),
    )

    # Every series goes through the adapter, stitched across whatever tags the
    # filer has used. Naming a us-gaap concept here would bake one company's
    # vocabulary into shared code.
    series = {
        name: resolve_value_series(extraction.facts, adapter, name)
        for name in adapter.concept_aliases()
    }
    balance_label = _balance_label(extraction.facts, period_label)

    def value(canonical: str, label: str | None) -> AnalyticalValue | None:
        if label is None:
            return None
        found = series.get(canonical, {}).get(label)
        return AnalyticalValue.from_fact(found) if found else None

    tax_rate = registry.get(TAX_ASSUMPTION)

    with calculation_graph() as graph:
        results = _compute(
            value=value,
            period_label=period_label,
            balance_label=balance_label,
            tax_rate=tax_rate,
        )

    # Reconcile over everything extracted, then keep only what the caller asked
    # to carry. Narrowing before the checks would weaken them silently.
    report = reconcile(
        extraction.facts,
        cumulative_concepts=concrete_concepts(adapter, adapter.cumulative_concepts()),
    )
    used_facts = _select_facts(
        extraction.facts,
        results,
        scope=facts_scope,
        period_label=period_label,
        balance_label=balance_label,
    )

    return AnalysisBundle(
        entity_id=entity_id,
        period_label=period_label,
        template=template,
        facts=used_facts,
        values=tuple(results),
        scenarios=tuple(scenarios),
        charts=build_specs(results, used_facts, entity_id=entity_id, has_scenario=bool(scenarios)),
        calculations=tuple(
            sorted(
                {
                    node.node_id: node
                    for node in (*graph.nodes, *(n for s in scenarios for n in s.calculations))
                }.values(),
                key=lambda n: n.node_id,
            )
        ),
        assumptions=(tax_rate,),
        validation=report,
        notes={
            "facts_scope": facts_scope.value,
            "facts_extracted": len(extraction.facts),
            "restatements": len(extraction.restatements),
            "skipped_entries": len(extraction.skipped),
            "segment_support": adapter.segment_support("sec_companyfacts").explanation,
        },
        provenance=BundleProvenance(
            created_at=datetime.now(UTC),
            package_version=__version__,
            command=command,
        ),
    )


def _compute(
    *,
    value: Any,
    period_label: str,
    balance_label: str | None,
    tax_rate: Assumption,
) -> list[AnalyticalValue]:
    cfo = value("cash_flow.operating", period_label)
    capex = value("capex.cash", period_label)
    depreciation = value("depreciation", period_label)
    operating_income = value("income.operating", period_label)
    revenue = value("revenue.total", period_label)

    results = [
        reported_fcf(cfo, capex),
        lease_adjusted_fcf(cfo, capex, value("capex.finance_lease_principal", period_label)),
        standardized_fcf(
            cfo,
            capex,
            value("capex.disposal_proceeds", period_label),
            value("capex.finance_lease_principal", period_label),
        ),
        capex_intensity(capex, revenue),
        capex_to_depreciation(capex, depreciation),
        net_investment(capex, depreciation),
    ]

    if balance_label is not None:
        profit = nopat(operating_income, tax_rate)
        operating_capital = invested_capital_operating(
            value("balance.assets", balance_label),
            value("balance.current_liabilities", balance_label),
        )
        capital_ex_cash = invested_capital_ex_cash(
            value("balance.assets", balance_label),
            value("balance.current_liabilities", balance_label),
            value("balance.cash", balance_label),
            value("balance.marketable_securities", balance_label),
        )
        results.extend(
            [
                profit,
                operating_capital,
                capital_ex_cash,
                roic(profit, operating_capital).model_copy(
                    update={"label": "return on invested capital (operating basis)"}
                ),
                roic(profit, capital_ex_cash).model_copy(
                    update={"label": "return on invested capital (excluding cash)"}
                ),
            ]
        )
    return results


def _balance_label(facts: Sequence[FinancialFact], period_label: str) -> str | None:
    """Find the balance-sheet date that closes *period_label*.

    Instants use their own label form, so the flow period cannot be reused
    directly. Matching on the closing date keeps a return ratio anchored to the
    capital that was actually in place when the period ended.
    """
    flow = [f for f in facts if f.period.label == period_label and f.period.end is not None]
    if not flow:
        return None
    closing = flow[0].period.end
    for fact in facts:
        if fact.period.kind is PeriodKind.INSTANT and fact.period.end == closing:
            return fact.period.label
    return None


def headline_table(bundle: AnalysisBundle) -> list[tuple[str, str, str]]:
    """Label, formatted value and status glyph, for display."""
    rows = []
    for item in bundle.values:
        rows.append((item.label or item.value_id, item.formatted, item.status.value))
    return rows
