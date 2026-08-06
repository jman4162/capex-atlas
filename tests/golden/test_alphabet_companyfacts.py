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
from capex_atlas.normalization.quarters import discrete_quarter
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
