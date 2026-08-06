from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from capex_atlas.normalization.calendar import KNOWN_CALENDARS, FiscalCalendar
from capex_atlas.normalization.quarters import (
    QuarterizationError,
    discrete_quarter,
    quarterize_series,
)
from capex_atlas.provenance.graph import calculation_graph
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.period import FiscalPeriod, PeriodKind
from capex_atlas.schemas.values import AnalyticalValue

CALENDAR_FILER = FiscalCalendar(entity_id="GOOGL", fiscal_year_end_month=12)
JUNE_FILER = FiscalCalendar(entity_id="MSFT", fiscal_year_end_month=6)


class TestCalendarYearFiler:
    @pytest.mark.parametrize(
        ("end", "quarter"),
        [
            (date(2026, 3, 31), 1),
            (date(2026, 6, 30), 2),
            (date(2026, 9, 30), 3),
            (date(2026, 12, 31), 4),
        ],
    )
    def test_quarters_match_the_calendar(self, end: date, quarter: int):
        assert CALENDAR_FILER.fiscal_quarter_for(end) == quarter
        assert CALENDAR_FILER.fiscal_year_for(end) == 2026


class TestJuneYearEndFiler:
    @pytest.mark.parametrize(
        ("end", "fiscal_year", "quarter"),
        [
            (date(2025, 9, 30), 2026, 1),
            (date(2025, 12, 31), 2026, 2),
            (date(2026, 3, 31), 2026, 3),
            (date(2026, 6, 30), 2026, 4),
            (date(2026, 9, 30), 2027, 1),
        ],
    )
    def test_fiscal_year_runs_ahead_of_the_calendar(
        self, end: date, fiscal_year: int, quarter: int
    ):
        # September 2025 is Microsoft's fiscal 2026 Q1, not calendar 2025 Q3.
        assert JUNE_FILER.fiscal_year_for(end) == fiscal_year
        assert JUNE_FILER.fiscal_quarter_for(end) == quarter

    def test_same_label_covers_different_months_than_a_calendar_filer(self):
        june_q2 = JUNE_FILER.period_for(date(2025, 10, 1), date(2025, 12, 31))
        calendar_q2 = CALENDAR_FILER.period_for(date(2026, 4, 1), date(2026, 6, 30))
        assert june_q2 is not None and calendar_q2 is not None
        assert june_q2.label == calendar_q2.label == "2026Q2"
        assert june_q2.end != calendar_q2.end


class TestPeriodClassification:
    def test_quarter_span(self):
        period = CALENDAR_FILER.period_for(date(2026, 4, 1), date(2026, 6, 30))
        assert period is not None
        assert period.kind is PeriodKind.QUARTER
        assert period.label == "2026Q2"

    def test_half_year_is_year_to_date(self):
        period = CALENDAR_FILER.period_for(date(2026, 1, 1), date(2026, 6, 30))
        assert period is not None
        assert period.kind is PeriodKind.YEAR_TO_DATE
        assert period.label == "2026YTD2"

    def test_nine_months_is_year_to_date(self):
        period = CALENDAR_FILER.period_for(date(2026, 1, 1), date(2026, 9, 30))
        assert period is not None
        assert period.label == "2026YTD3"

    def test_full_year(self):
        period = CALENDAR_FILER.period_for(date(2026, 1, 1), date(2026, 12, 31))
        assert period is not None
        assert period.kind is PeriodKind.FISCAL_YEAR
        assert period.label == "2026FY"

    def test_instant_has_no_start(self):
        period = CALENDAR_FILER.period_for(None, date(2026, 6, 30))
        assert period is not None
        assert period.kind is PeriodKind.INSTANT

    def test_odd_spans_are_rejected_rather_than_forced(self):
        # An eight-month transition period is not a quarter and not a year.
        assert CALENDAR_FILER.period_for(date(2026, 1, 1), date(2026, 8, 31)) is None

    def test_fifty_three_week_quarter_still_classifies(self):
        period = CALENDAR_FILER.period_for(date(2026, 4, 1), date(2026, 7, 4))
        assert period is not None
        assert period.kind is PeriodKind.QUARTER


def test_known_calendars_exclude_amazon():
    assert "AMZN" not in KNOWN_CALENDARS
    assert set(KNOWN_CALENDARS) == {"GOOGL", "META", "MSFT", "ORCL"}


def cumulative(amount: str, quarter: int, *, year: int = 2026) -> AnalyticalValue:
    kind = PeriodKind.QUARTER if quarter == 1 else PeriodKind.YEAR_TO_DATE
    period = FiscalPeriod(fiscal_year=year, fiscal_quarter=quarter, kind=kind)
    return AnalyticalValue(
        value_id=f"ytd-{year}-{quarter}",
        value=Decimal(amount),
        unit="USD",
        status=EvidenceStatus.REPORTED,
        period=period,
    )


class TestQuarterization:
    def test_fourth_quarter_backs_out_of_the_annual_total(self):
        annual = cumulative("1000", 4)
        nine_months = cumulative("700", 3)
        q4 = FiscalPeriod(fiscal_year=2026, fiscal_quarter=4)
        result = discrete_quarter(annual, nine_months, quarter=q4)
        assert result.value == Decimal("300")
        assert result.period is not None
        assert result.period.label == "2026Q4"

    def test_derived_quarters_are_not_reported(self):
        result = discrete_quarter(
            cumulative("1000", 4),
            cumulative("700", 3),
            quarter=FiscalPeriod(fiscal_year=2026, fiscal_quarter=4),
        )
        assert result.status is EvidenceStatus.DERIVED

    def test_refuses_to_derive_a_non_quarter(self):
        annual = FiscalPeriod(fiscal_year=2026, kind=PeriodKind.FISCAL_YEAR)
        with pytest.raises(QuarterizationError, match="expected a quarter"):
            discrete_quarter(cumulative("1000", 4), cumulative("700", 3), quarter=annual)

    def test_series_produces_four_quarters(self):
        series = {
            1: cumulative("100", 1),
            2: cumulative("250", 2),
            3: cumulative("430", 3),
            4: cumulative("700", 4),
        }
        discrete = quarterize_series(series, fiscal_year=2026)
        assert [discrete[i].value for i in (1, 2, 3, 4)] == [
            Decimal("100"),
            Decimal("150"),
            Decimal("180"),
            Decimal("270"),
        ]

    def test_first_quarter_passes_through_as_reported(self):
        discrete = quarterize_series({1: cumulative("100", 1)}, fiscal_year=2026)
        assert discrete[1].status is EvidenceStatus.REPORTED

    def test_gaps_are_left_empty_rather_than_guessed(self):
        # No 6-month figure, so Q3 cannot be derived and is simply absent.
        discrete = quarterize_series(
            {1: cumulative("100", 1), 3: cumulative("430", 3)}, fiscal_year=2026
        )
        assert set(discrete) == {1}

    def test_quarters_are_traced(self):
        with calculation_graph() as graph:
            quarterize_series({1: cumulative("100", 1), 2: cumulative("250", 2)}, fiscal_year=2026)
        assert len(graph) == 1
        assert graph.nodes[0].formula == "year_to_date(n) - year_to_date(n-1)"
