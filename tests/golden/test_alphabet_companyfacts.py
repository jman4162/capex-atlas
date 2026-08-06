"""End-to-end extraction against a real Alphabet Company Facts payload.

The fixture is a trimmed copy of SEC EDGAR's Company Facts response for CIK
1652044, public domain, hash-pinned in ``tests/fixtures/manifest.json``. Tests
never reach the network.

Values asserted here were read from that fixture. They are checks on the
extraction pipeline, not published analysis.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from capex_atlas.accounting.reconciliation import CheckStatus, reconcile
from capex_atlas.adapters.alphabet import AlphabetAdapter
from capex_atlas.adapters.base import resolve_series
from capex_atlas.assumptions.registry import AssumptionRegistry
from capex_atlas.metrics import (
    capex_to_depreciation,
    invested_capital_ex_cash,
    invested_capital_operating,
    lease_adjusted_fcf,
    nopat,
    reported_fcf,
    roic,
    standardized_fcf,
)
from capex_atlas.normalization.quarters import discrete_quarter
from capex_atlas.provenance.graph import calculation_graph
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.period import FiscalPeriod
from capex_atlas.schemas.source import SourceKind, SourceReference
from capex_atlas.schemas.values import AnalyticalValue
from capex_atlas.xbrl.companyfacts import extract_facts

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_NAME = "googl_companyfacts_trimmed.json"

CAPEX = "PaymentsToAcquirePropertyPlantAndEquipment"
CFO = "NetCashProvidedByUsedInOperatingActivities"


@pytest.fixture(scope="module")
def payload() -> dict[str, object]:
    body = (FIXTURES / FIXTURE_NAME).read_text()
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    expected = manifest[FIXTURE_NAME]["sha256"]
    actual = hashlib.sha256(body.encode()).hexdigest()
    assert actual == expected, "fixture changed; re-pin the hash deliberately"
    loaded: dict[str, object] = json.loads(body)
    return loaded


@pytest.fixture(scope="module")
def extraction(payload: dict[str, object]):  # type: ignore[no-untyped-def]
    adapter = AlphabetAdapter()
    source = SourceReference(
        kind=SourceKind.SEC_FILING,
        url="https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json",
    )
    return extract_facts(
        payload,  # type: ignore[arg-type]
        entity_id=adapter.entity_id,
        calendar=adapter.calendar(),
        source=source,
        statement_map=adapter.statement_map(),
    )


def test_fixture_is_alphabet(payload: dict[str, object]):
    assert payload["entityName"] == "Alphabet Inc."
    assert payload["cik"] == 1652044


def test_extraction_produces_facts(extraction):  # type: ignore[no-untyped-def]
    assert len(extraction.facts) > 100
    assert extraction.skipped == ()


def test_every_fact_carries_a_citation(extraction):  # type: ignore[no-untyped-def]
    for fact in extraction.facts:
        assert fact.source.accession, f"{fact.metric_id} {fact.period.label} has no accession"
        assert fact.source.is_verifiable


class TestRealPeriods:
    def test_comparatives_land_in_their_own_years(self, extraction):  # type: ignore[no-untyped-def]
        # Alphabet's fiscal-2025 10-K reports 2024 capex as a comparative, tagged
        # fy 2025. It must not be filed under 2025.
        labels = {f.period.label for f in extraction.by_concept(CAPEX)}
        assert {"2024FY", "2025FY"} <= labels

    def test_annual_and_quarterly_capex_are_distinct_facts(self, extraction):  # type: ignore[no-untyped-def]
        by_label = {f.period.label: f.value for f in extraction.by_concept(CAPEX)}
        assert by_label["2025FY"] == Decimal("91447000000")
        assert by_label["2026Q1"] == Decimal("35674000000")
        assert by_label["2026YTD2"] == Decimal("80598000000")


class TestQuarterizationOnRealData:
    def test_second_quarter_backs_out_of_the_half_year(self, extraction):  # type: ignore[no-untyped-def]
        by_label = {f.period.label: f for f in extraction.by_concept(CAPEX)}
        half = AnalyticalValue.from_fact(by_label["2026YTD2"])
        first = AnalyticalValue.from_fact(by_label["2026Q1"])
        q2 = discrete_quarter(half, first, quarter=FiscalPeriod(fiscal_year=2026, fiscal_quarter=2))
        # 80,598 - 35,674, in millions of dollars.
        assert q2.value == Decimal("44924000000")

    def test_the_derived_quarter_is_not_presented_as_reported(self, extraction):  # type: ignore[no-untyped-def]
        by_label = {f.period.label: f for f in extraction.by_concept(CAPEX)}
        q2 = discrete_quarter(
            AnalyticalValue.from_fact(by_label["2026YTD2"]),
            AnalyticalValue.from_fact(by_label["2026Q1"]),
            quarter=FiscalPeriod(fiscal_year=2026, fiscal_quarter=2),
        )
        assert q2.status.value == "derived"


class TestReconciliation:
    def test_balance_sheet_identity_holds_at_every_date(self, extraction):  # type: ignore[no-untyped-def]
        report = reconcile(extraction.facts)
        assert report.passed, [f.detail for f in report.failures]
        assert report.verified_count > 0

    def test_cumulative_capex_never_shrinks_within_a_year(self, extraction):  # type: ignore[no-untyped-def]
        report = reconcile(extraction.facts, cumulative_concepts=[CAPEX, CFO])
        assert report.passed, [f.detail for f in report.failures]
        # Guard against the check quietly examining nothing, which is how this
        # test passed while verifying zero cumulative series.
        cumulative_checks = [r for r in report.results if r.check == "ytd_monotonic"]
        assert len(cumulative_checks) >= 10
        assert all(r.status is CheckStatus.PASSED for r in cumulative_checks)

    def test_extracted_facts_keep_their_dates(self, extraction):  # type: ignore[no-untyped-def]
        half_year = next(f for f in extraction.by_concept(CAPEX) if f.period.label == "2026YTD2")
        assert half_year.period.start is not None
        assert half_year.period.end is not None

    def test_skips_are_not_counted_as_verification(self, extraction):  # type: ignore[no-untyped-def]
        report = reconcile(extraction.facts)
        skipped = [r for r in report.results if r.status is CheckStatus.SKIPPED]
        assert report.verified_count == len(report.results) - len(skipped)


class TestAdapter:
    def test_segment_gap_is_reported_rather_than_returned_empty(self):
        support = AlphabetAdapter().segment_support("sec_companyfacts")
        assert support.availability.value == "not_in_source"
        assert "dimensions" in support.explanation
        assert "Google Cloud" in support.known_segments

    def test_capex_concepts_exclude_finance_leases(self):
        # Finance-lease additions are capital deployment but not cash capex.
        # Combining them is a named choice made in the metrics layer.
        assert "FinanceLeaseLiability" not in AlphabetAdapter().capex_concepts()


class TestMetricsOnRealData:
    """Metrics over the pinned fixture.

    These assertions check that the pipeline computes what the filings imply.
    They are not published analysis of Alphabet, and the figures carry the
    disclaimer that applies to everything this package produces.
    """

    @pytest.fixture
    def values(self, extraction):  # type: ignore[no-untyped-def]
        indexed = {
            (f.metric_id, f.period.label): AnalyticalValue.from_fact(f) for f in extraction.facts
        }
        revenue = {
            label: AnalyticalValue.from_fact(fact)
            for label, fact in resolve_series(
                extraction.facts, AlphabetAdapter().concept_aliases()["revenue.total"]
            ).items()
        }
        return indexed, revenue

    def test_revenue_series_spans_the_tag_migration(self, values):  # type: ignore[no-untyped-def]
        # Alphabet moved from RevenueFromContractWithCustomer... to Revenues
        # after 2025Q1. Either tag alone leaves a hole in the history.
        _, revenue = values
        annual = {label for label in revenue if label.endswith("FY")}
        assert {"2023FY", "2024FY", "2025FY"} <= annual

    def test_free_cash_flow_variants_differ_by_the_lease_payments(self, values):  # type: ignore[no-untyped-def]
        indexed, _ = values
        cfo = indexed[(CFO, "2025FY")]
        capex = indexed[(CAPEX, "2025FY")]
        leases = indexed[("FinanceLeasePrincipalPayments", "2025FY")]
        plain = reported_fcf(cfo, capex)
        adjusted = lease_adjusted_fcf(cfo, capex, leases)
        assert plain.value == Decimal("73266000000")
        assert adjusted.value == Decimal("71278000000")
        assert plain.value - adjusted.value == leases.value

    def test_untagged_input_yields_unresolved_rather_than_a_wrong_number(self, values):  # type: ignore[no-untyped-def]
        # Alphabet does not tag proceeds from equipment disposals in this
        # period, so the standardized definition cannot be computed. It must
        # come back unknown instead of silently treating the gap as zero.
        indexed, _ = values
        result = standardized_fcf(
            indexed[(CFO, "2025FY")],
            indexed[(CAPEX, "2025FY")],
            indexed.get(("ProceedsFromSaleOfPropertyPlantAndEquipment", "2025FY")),
            indexed[("FinanceLeasePrincipalPayments", "2025FY")],
        )
        assert result.value is None
        assert result.status is EvidenceStatus.UNRESOLVED

    def test_capex_runs_well_above_depreciation(self, values):  # type: ignore[no-untyped-def]
        indexed, _ = values
        ratio = capex_to_depreciation(
            indexed[(CAPEX, "2025FY")], indexed[("Depreciation", "2025FY")]
        )
        assert ratio.value is not None
        assert ratio.value > Decimal("4")
        assert ratio.status is EvidenceStatus.DERIVED

    def test_statutory_tax_rate_makes_returns_estimated_not_derived(self, values):  # type: ignore[no-untyped-def]
        indexed, _ = values
        rate = AssumptionRegistry.load().get("tax.us_federal_statutory_rate")
        profit = nopat(indexed[("OperatingIncomeLoss", "2025FY")], rate)
        capital = invested_capital_operating(
            indexed[("Assets", "2025@4")], indexed[("LiabilitiesCurrent", "2025@4")]
        )
        result = roic(profit, capital)
        assert capital.status is EvidenceStatus.DERIVED
        assert result.status is EvidenceStatus.ESTIMATED

    def test_a_return_ratio_takes_the_period_of_its_flow(self, values):  # type: ignore[no-untyped-def]
        # NOPAT spans a year, invested capital is measured at a date. The ratio
        # describes the year.
        indexed, _ = values
        rate = AssumptionRegistry.load().get("tax.us_federal_statutory_rate")
        result = roic(
            nopat(indexed[("OperatingIncomeLoss", "2025FY")], rate),
            invested_capital_operating(
                indexed[("Assets", "2025@4")], indexed[("LiabilitiesCurrent", "2025@4")]
            ),
        )
        assert result.period is not None
        assert result.period.label == "2025FY"

    def test_the_two_capital_bases_give_materially_different_returns(self, values):  # type: ignore[no-untyped-def]
        # Several percentage points apart, which is why the package names both
        # rather than picking one and calling it "ROIC".
        indexed, _ = values
        rate = AssumptionRegistry.load().get("tax.us_federal_statutory_rate")
        profit = nopat(indexed[("OperatingIncomeLoss", "2025FY")], rate)
        including_cash = roic(
            profit,
            invested_capital_operating(
                indexed[("Assets", "2025@4")], indexed[("LiabilitiesCurrent", "2025@4")]
            ),
        )
        excluding_cash = roic(
            profit,
            invested_capital_ex_cash(
                indexed[("Assets", "2025@4")],
                indexed[("LiabilitiesCurrent", "2025@4")],
                indexed[("CashAndCashEquivalentsAtCarryingValue", "2025@4")],
                indexed[("MarketableSecuritiesCurrent", "2025@4")],
            ),
        )
        assert including_cash.value is not None and excluding_cash.value is not None
        assert excluding_cash.value - including_cash.value > Decimal("0.05")

    def test_every_metric_result_traces_to_the_filing(self, values):  # type: ignore[no-untyped-def]
        indexed, _ = values
        with calculation_graph() as graph:
            result = reported_fcf(indexed[(CFO, "2025FY")], indexed[(CAPEX, "2025FY")])
        assert graph.leaf_source_ids(result.value_id)
