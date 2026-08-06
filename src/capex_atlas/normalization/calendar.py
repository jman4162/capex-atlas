"""Mapping real dates onto a filer's own fiscal calendar.

Alphabet's 2026Q2 and Microsoft's 2026Q2 cover different months, so a comparison
that treats the labels as equivalent is wrong before any arithmetic happens. Every
period in the package therefore comes from a filer-specific calendar rather than
from the calendar year.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from capex_atlas.schemas.period import FiscalPeriod, PeriodKind

MONTHS_PER_QUARTER = 3
MONTHS_PER_YEAR = 12

QUARTER_DAYS = (85, 96)
"""Plausible day span for one quarter, wide enough for 52/53-week filers."""

HALF_DAYS = (175, 190)
NINE_MONTH_DAYS = (265, 285)
YEAR_DAYS = (350, 380)


class FiscalCalendar(BaseModel):
    """Where a filer's fiscal year ends.

    Only the month is modelled. A 52/53-week filer whose year-end drifts by a few
    days still lands in the right fiscal quarter, and the exact dates travel on
    the period itself.
    """

    model_config = ConfigDict(frozen=True)

    entity_id: str
    fiscal_year_end_month: int = Field(ge=1, le=MONTHS_PER_YEAR)

    def fiscal_year_for(self, period_end: date) -> int:
        """Fiscal year containing *period_end*.

        A December year-end makes fiscal and calendar years identical. Otherwise
        months after the year-end belong to the next fiscal year: for a June
        year-end, September 2025 falls in fiscal 2026.
        """
        if self.fiscal_year_end_month == MONTHS_PER_YEAR:
            return period_end.year
        return (
            period_end.year
            if period_end.month <= self.fiscal_year_end_month
            else period_end.year + 1
        )

    def fiscal_quarter_for(self, period_end: date) -> int:
        """Which fiscal quarter *period_end* closes."""
        offset = (period_end.month - self.fiscal_year_end_month - 1) % MONTHS_PER_YEAR
        return offset // MONTHS_PER_QUARTER + 1

    def period_for(self, start: date | None, end: date) -> FiscalPeriod | None:
        """Classify a reported span, or return ``None`` if it fits no clean bucket.

        Unclassifiable spans happen often in XBRL: eight-month transition
        periods, cumulative multi-year figures, oddly tagged facts. Dropping them
        loudly beats forcing them into a quarter they do not occupy.
        """
        fiscal_year = self.fiscal_year_for(end)
        quarter = self.fiscal_quarter_for(end)

        if start is None:
            return FiscalPeriod(
                fiscal_year=fiscal_year,
                fiscal_quarter=quarter,
                kind=PeriodKind.INSTANT,
                start=None,
                end=end,
            )

        days = (end - start).days + 1
        if _within(days, QUARTER_DAYS):
            kind, needs_quarter = PeriodKind.QUARTER, True
        elif _within(days, HALF_DAYS) or _within(days, NINE_MONTH_DAYS):
            kind, needs_quarter = PeriodKind.YEAR_TO_DATE, True
        elif _within(days, YEAR_DAYS):
            kind, needs_quarter = PeriodKind.FISCAL_YEAR, False
        else:
            return None

        return FiscalPeriod(
            fiscal_year=fiscal_year,
            fiscal_quarter=quarter if needs_quarter else None,
            kind=kind,
            start=start,
            end=end,
        )


def _within(days: int, bounds: tuple[int, int]) -> bool:
    return bounds[0] <= days <= bounds[1]


CALENDAR_YEAR_END = 12

KNOWN_CALENDARS: dict[str, FiscalCalendar] = {
    "GOOGL": FiscalCalendar(entity_id="GOOGL", fiscal_year_end_month=CALENDAR_YEAR_END),
    "META": FiscalCalendar(entity_id="META", fiscal_year_end_month=CALENDAR_YEAR_END),
    "MSFT": FiscalCalendar(entity_id="MSFT", fiscal_year_end_month=6),
    "ORCL": FiscalCalendar(entity_id="ORCL", fiscal_year_end_month=5),
}
"""Fiscal year ends for covered filers.

Each is stated in the filer's own 10-K cover page. Amazon and AWS are out of
scope for this package; see DISCLOSURE.md.
"""
