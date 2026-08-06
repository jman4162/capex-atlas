"""Recovering discrete quarters from year-to-date reporting.

Cash-flow and income-statement items are frequently tagged cumulatively, so a
filer's Q3 cash flow may exist only as a nine-month figure. The fourth quarter is
the usual casualty: it is almost never reported on its own and has to be backed
out of the annual total.

The subtraction is a calculation, not a reading, so it runs through the metric
kernel and the result carries derived status with a node a reader can inspect.
"""

from __future__ import annotations

from decimal import Decimal

from capex_atlas.provenance.metric import INHERIT, OUTPUT_PERIOD_KWARG, metric
from capex_atlas.schemas.period import FiscalPeriod, PeriodKind
from capex_atlas.schemas.values import AnalyticalValue


class QuarterizationError(ValueError):
    pass


@metric(
    metric_id="period.discrete_quarter",
    version="1.0.0",
    formula="year_to_date(n) - year_to_date(n-1)",
    unit=INHERIT,
    label="discrete quarter",
    homogeneous_inputs=True,
    allow_mixed_periods=True,
)
def _difference(later: Decimal, earlier: Decimal) -> Decimal:
    return later - earlier


def discrete_quarter(
    cumulative: AnalyticalValue,
    prior_cumulative: AnalyticalValue,
    *,
    quarter: FiscalPeriod,
) -> AnalyticalValue:
    """Back one quarter out of two cumulative figures.

    ``Q4 = FY - 9M`` is the common case; ``Q3 = 9M - 6M`` works the same way.
    """
    if quarter.kind is not PeriodKind.QUARTER:
        raise QuarterizationError(f"expected a quarter to derive, got {quarter.kind}")
    return _difference(cumulative, prior_cumulative, **{OUTPUT_PERIOD_KWARG: quarter})


def quarterize_series(
    cumulative_by_quarter: dict[int, AnalyticalValue],
    *,
    fiscal_year: int,
) -> dict[int, AnalyticalValue]:
    """Turn ``{1: Q1, 2: H1, 3: 9M, 4: FY}`` into four discrete quarters.

    Quarters whose predecessor is missing are left out rather than guessed. A
    partial series is a normal state mid-year, and inventing the gap would
    manufacture a fact.
    """
    discrete: dict[int, AnalyticalValue] = {}
    for index in sorted(cumulative_by_quarter):
        current = cumulative_by_quarter[index]
        if index == 1:
            # The first quarter's cumulative figure is already discrete.
            discrete[index] = current
            continue
        previous = cumulative_by_quarter.get(index - 1)
        if previous is None:
            continue
        period = FiscalPeriod(
            fiscal_year=fiscal_year,
            fiscal_quarter=index,
            kind=PeriodKind.QUARTER,
            start=None,
            end=current.period.end if current.period else None,
        )
        discrete[index] = discrete_quarter(current, previous, quarter=period)
    return discrete
