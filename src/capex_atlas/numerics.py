"""Discounting and root-finding.

Deliberately outside the modelling packages, and therefore outside the uncited-
constant scan. The numbers in this file are properties of the algorithms
(iteration caps, convergence tolerances, search brackets), not claims about any
company, and citing a bisection tolerance to a filing would be nonsense.

The boundary only holds if it is respected: nothing with economic meaning belongs
here. A useful life, a margin, a ramp or a discount rate is a modelling
parameter, lives in the assumption registry, and is passed in.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, localcontext

from capex_atlas.schemas.decimals import calculation_context

MAX_ITERATIONS = 200
CONVERGENCE_TOLERANCE = Decimal("0.0000000001")
IRR_LOWER_BOUND = Decimal("-0.9999")
IRR_UPPER_BOUND = Decimal("10")


def net_present_value(cash_flows: Sequence[Decimal], discount_rate: Decimal) -> Decimal:
    """Discount a series whose first element sits at period zero."""
    with localcontext(calculation_context()):
        total = Decimal(0)
        factor = Decimal(1)
        base = Decimal(1) + discount_rate
        for flow in cash_flows:
            total += flow / factor
            factor *= base
        return total


def internal_rate_of_return(cash_flows: Sequence[Decimal]) -> Decimal | None:
    """Rate at which the series discounts to zero, or ``None`` when undefined.

    Bisection rather than Newton: slower, but it cannot diverge, and these series
    are short. Returns ``None`` when the cash flows never change sign, when no
    root lies in the bracket, or when the series is degenerate. A project that
    never turns cash-positive has no rate of return, and inventing one would be
    worse than admitting it.
    """
    if not cash_flows or all(flow == 0 for flow in cash_flows):
        return None
    if not (any(f > 0 for f in cash_flows) and any(f < 0 for f in cash_flows)):
        return None

    low, high = IRR_LOWER_BOUND, IRR_UPPER_BOUND
    value_low = net_present_value(cash_flows, low)
    value_high = net_present_value(cash_flows, high)
    if value_low * value_high > 0:
        return None

    for _ in range(MAX_ITERATIONS):
        middle = (low + high) / 2
        value_middle = net_present_value(cash_flows, middle)
        if abs(value_middle) < CONVERGENCE_TOLERANCE or (high - low) < CONVERGENCE_TOLERANCE:
            return middle
        if value_low * value_middle < 0:
            high, value_high = middle, value_middle
        else:
            low, value_low = middle, value_middle
    return (low + high) / 2


def payback_period(cash_flows: Sequence[Decimal]) -> Decimal | None:
    """Periods until cumulative cash turns positive, interpolated within the year.

    ``None`` when the series never recovers its outlay over the horizon modelled,
    which is a meaningful answer during a build-out rather than a missing one.
    """
    cumulative = Decimal(0)
    with localcontext(calculation_context()):
        for index, flow in enumerate(cash_flows):
            previous = cumulative
            cumulative += flow
            if cumulative >= 0 and index > 0 and previous < 0:
                if flow == 0:
                    return Decimal(index)
                return Decimal(index - 1) + (-previous / flow)
    return None


def solve_for_root(
    evaluate: object,
    low: Decimal,
    high: Decimal,
) -> Decimal | None:
    """Find x in [low, high] where ``evaluate(x)`` is zero, by bisection.

    ``None`` when the endpoints do not bracket a sign change, meaning no value in
    the searched range satisfies the condition. That is a real finding: it says
    the claim cannot be met anywhere in the plausible range.
    """
    assert callable(evaluate)
    value_low = evaluate(low)
    value_high = evaluate(high)
    if value_low is None or value_high is None:
        return None
    if value_low == 0:
        return low
    if value_high == 0:
        return high
    if value_low * value_high > 0:
        return None

    for _ in range(MAX_ITERATIONS):
        middle = (low + high) / 2
        value_middle = evaluate(middle)
        if value_middle is None:
            return None
        if abs(value_middle) < CONVERGENCE_TOLERANCE or (high - low) < CONVERGENCE_TOLERANCE:
            return middle
        if value_low * value_middle < 0:
            high = middle
        else:
            low, value_low = middle, value_middle
    return (low + high) / 2
