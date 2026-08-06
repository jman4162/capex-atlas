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
from typing import Any

from capex_atlas import __version__
from capex_atlas.accounting.reconciliation import reconcile
from capex_atlas.adapters.alphabet import AlphabetAdapter
from capex_atlas.adapters.base import resolve_series
from capex_atlas.assumptions.models import Assumption
from capex_atlas.assumptions.registry import AssumptionRegistry
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
from capex_atlas.schemas.facts import FinancialFact
from capex_atlas.schemas.period import PeriodKind
from capex_atlas.schemas.source import SourceReference
from capex_atlas.schemas.values import AnalyticalValue
from capex_atlas.xbrl.companyfacts import extract_facts

ADAPTERS: dict[str, AlphabetAdapter] = {"GOOGL": AlphabetAdapter()}

CFO = "NetCashProvidedByUsedInOperatingActivities"
CAPEX = "PaymentsToAcquirePropertyPlantAndEquipment"
DISPOSALS = "ProceedsFromSaleOfPropertyPlantAndEquipment"
LEASE_PRINCIPAL = "FinanceLeasePrincipalPayments"
DEPRECIATION = "Depreciation"
OPERATING_INCOME = "OperatingIncomeLoss"
ASSETS = "Assets"
CURRENT_LIABILITIES = "LiabilitiesCurrent"
CASH = "CashAndCashEquivalentsAtCarryingValue"
SECURITIES = "MarketableSecuritiesCurrent"

TAX_ASSUMPTION = "tax.us_federal_statutory_rate"


class UnsupportedEntityError(KeyError):
    pass


def build_analysis(
    payload: dict[str, Any],
    *,
    entity_id: str,
    period_label: str,
    source: SourceReference,
    registry: AssumptionRegistry | None = None,
    template: str = "capital-deployment",
    command: str | None = None,
) -> AnalysisBundle:
    """Turn a Company Facts payload into a frozen analysis for one period."""
    adapter = ADAPTERS.get(entity_id)
    if adapter is None:
        raise UnsupportedEntityError(
            f"no adapter for {entity_id!r}. Covered filers: {sorted(ADAPTERS)}. "
            "Amazon and AWS are out of scope; see DISCLOSURE.md."
        )

    registry = registry or AssumptionRegistry.load()
    extraction = extract_facts(
        payload,
        entity_id=entity_id,
        calendar=adapter.calendar(),
        source=source,
        statement_map=adapter.statement_map(),
    )

    indexed = {(f.metric_id, f.period.label): f for f in extraction.facts}
    revenue_series = resolve_series(extraction.facts, adapter.concept_aliases()["revenue.total"])
    balance_label = _balance_label(extraction.facts, period_label)

    def fact(concept: str, label: str) -> FinancialFact | None:
        return indexed.get((concept, label))

    def value(concept: str, label: str) -> AnalyticalValue | None:
        found = fact(concept, label)
        return AnalyticalValue.from_fact(found) if found else None

    revenue_fact = revenue_series.get(period_label)
    revenue = AnalyticalValue.from_fact(revenue_fact) if revenue_fact else None
    tax_rate = registry.get(TAX_ASSUMPTION)

    with calculation_graph() as graph:
        results = _compute(
            value=value,
            revenue=revenue,
            period_label=period_label,
            balance_label=balance_label,
            tax_rate=tax_rate,
        )

    used_facts = tuple(sorted(extraction.facts, key=lambda f: (f.metric_id, f.period.label)))
    report = reconcile(extraction.facts, cumulative_concepts=[CAPEX, CFO])

    return AnalysisBundle(
        entity_id=entity_id,
        period_label=period_label,
        template=template,
        facts=used_facts,
        values=tuple(results),
        calculations=tuple(sorted(graph.nodes, key=lambda n: n.node_id)),
        assumptions=(tax_rate,),
        validation=report,
        notes={
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
    revenue: AnalyticalValue | None,
    period_label: str,
    balance_label: str | None,
    tax_rate: Assumption,
) -> list[AnalyticalValue]:
    cfo = value(CFO, period_label)
    capex = value(CAPEX, period_label)
    depreciation = value(DEPRECIATION, period_label)
    operating_income = value(OPERATING_INCOME, period_label)

    results = [
        reported_fcf(cfo, capex),
        lease_adjusted_fcf(cfo, capex, value(LEASE_PRINCIPAL, period_label)),
        standardized_fcf(
            cfo,
            capex,
            value(DISPOSALS, period_label),
            value(LEASE_PRINCIPAL, period_label),
        ),
        capex_intensity(capex, revenue),
        capex_to_depreciation(capex, depreciation),
        net_investment(capex, depreciation),
    ]

    if balance_label is not None:
        profit = nopat(operating_income, tax_rate)
        operating_capital = invested_capital_operating(
            value(ASSETS, balance_label), value(CURRENT_LIABILITIES, balance_label)
        )
        capital_ex_cash = invested_capital_ex_cash(
            value(ASSETS, balance_label),
            value(CURRENT_LIABILITIES, balance_label),
            value(CASH, balance_label),
            value(SECURITIES, balance_label),
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
