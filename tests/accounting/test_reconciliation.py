from __future__ import annotations

from datetime import date
from decimal import Decimal

from capex_atlas.accounting.reconciliation import (
    CheckStatus,
    check_balance_sheet,
    check_year_to_date_consistency,
    reconcile,
)
from capex_atlas.schemas.facts import FinancialFact, Statement
from capex_atlas.schemas.period import FiscalPeriod, PeriodKind
from capex_atlas.schemas.source import SourceKind, SourceReference

SOURCE = SourceReference(kind=SourceKind.SEC_FILING, accession="0001-26-1", section="Statements")


def instant(concept: str, amount: str, *, year: int = 2026, quarter: int = 4) -> FinancialFact:
    return FinancialFact(
        entity_id="EXMPL",
        metric_id=concept,
        value=Decimal(amount),
        unit="USD",
        period=FiscalPeriod(
            fiscal_year=year,
            fiscal_quarter=quarter,
            kind=PeriodKind.INSTANT,
            end=date(year, quarter * 3, 28),
        ),
        statement=Statement.BALANCE_SHEET,
        source=SOURCE,
    )


def cumulative(concept: str, amount: str, quarters: int, *, year: int = 2026) -> FinancialFact:
    if quarters == 1:
        kind = PeriodKind.QUARTER
    elif quarters == 4:
        kind = PeriodKind.FISCAL_YEAR
    else:
        kind = PeriodKind.YEAR_TO_DATE
    return FinancialFact(
        entity_id="EXMPL",
        metric_id=concept,
        value=Decimal(amount),
        unit="USD",
        period=FiscalPeriod(
            fiscal_year=year,
            fiscal_quarter=None if kind is PeriodKind.FISCAL_YEAR else quarters,
            kind=kind,
            start=date(year, 1, 1),
            end=date(year, quarters * 3, 28),
        ),
        statement=Statement.CASH_FLOW,
        source=SOURCE,
    )


class TestBalanceSheet:
    def test_identity_holds(self):
        facts = [
            instant("Assets", "300"),
            instant("Liabilities", "180"),
            instant("StockholdersEquity", "120"),
        ]
        [result] = check_balance_sheet(facts)
        assert result.status is CheckStatus.PASSED

    def test_identity_broken_is_reported_with_the_gap(self):
        facts = [
            instant("Assets", "300"),
            instant("Liabilities", "180"),
            instant("StockholdersEquity", "100"),
        ]
        [result] = check_balance_sheet(facts)
        assert result.status is CheckStatus.FAILED
        assert result.difference == Decimal("20")
        assert "300" in result.detail

    def test_rounding_is_tolerated(self):
        facts = [
            instant("Assets", "300"),
            instant("Liabilities", "180"),
            instant("StockholdersEquity", "119"),
        ]
        [result] = check_balance_sheet(facts, tolerance=Decimal("1"))
        assert result.status is CheckStatus.PASSED

    def test_missing_inputs_skip_rather_than_pass(self):
        [result] = check_balance_sheet([instant("Assets", "300")])
        assert result.status is CheckStatus.SKIPPED
        assert result.ok  # not a failure...
        # ...but it must not be counted as verification.
        assert reconcile([instant("Assets", "300")]).verified_count == 0


class TestYearToDateConsistency:
    def test_growing_series_passes(self):
        facts = [
            cumulative("capex", "100", 1),
            cumulative("capex", "250", 2),
            cumulative("capex", "430", 3),
            cumulative("capex", "700", 4),
        ]
        results = check_year_to_date_consistency(facts, "capex")
        assert len(results) == 3
        assert all(r.status is CheckStatus.PASSED for r in results)

    def test_shrinking_series_fails(self):
        facts = [cumulative("capex", "250", 2), cumulative("capex", "180", 3)]
        [result] = check_year_to_date_consistency(facts, "capex")
        assert result.status is CheckStatus.FAILED
        assert "cumulative fell" in result.detail

    def test_negative_outflow_convention_is_handled(self):
        # Some filers report purchases as negative. Magnitude is what grows.
        facts = [cumulative("capex", "-100", 1), cumulative("capex", "-250", 2)]
        [result] = check_year_to_date_consistency(facts, "capex")
        assert result.status is CheckStatus.PASSED

    def test_discrete_middle_quarters_take_no_part(self):
        standalone_q3 = FinancialFact(
            entity_id="EXMPL",
            metric_id="capex",
            value=Decimal("180"),
            unit="USD",
            period=FiscalPeriod(
                fiscal_year=2026,
                fiscal_quarter=3,
                kind=PeriodKind.QUARTER,
                start=date(2026, 7, 1),
                end=date(2026, 9, 30),
            ),
            statement=Statement.CASH_FLOW,
            source=SOURCE,
        )
        facts = [cumulative("capex", "100", 1), cumulative("capex", "250", 2), standalone_q3]
        results = check_year_to_date_consistency(facts, "capex")
        # Q1 -> H1 only; the discrete Q3 is smaller than H1 and would look like
        # a failure if it were treated as cumulative.
        assert len(results) == 1
        assert results[0].status is CheckStatus.PASSED

    def test_absent_concept_reports_that_nothing_was_checked(self):
        # A check that examines nothing must say so. A silent empty result reads
        # as verification that never happened.
        [result] = check_year_to_date_consistency([], "capex")
        assert result.status is CheckStatus.SKIPPED
        assert "no cumulative periods" in result.detail

    def test_single_point_year_is_skipped(self):
        [result] = check_year_to_date_consistency([cumulative("capex", "100", 1)], "capex")
        assert result.status is CheckStatus.SKIPPED


def test_report_separates_verification_from_absence():
    facts = [
        instant("Assets", "300"),
        instant("Liabilities", "180"),
        instant("StockholdersEquity", "120"),
    ]
    report = reconcile(facts, cumulative_concepts=["capex"])
    assert report.passed
    assert report.verified_count == 1  # the balance sheet, not the absent capex series
    assert len(report.results) == 2
