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
RESIDUAL_FRACTION = Decimal("0.000001")
"""How near zero a collapsed interval's value must be, relative to the starting
scale, to count as a root rather than a jump."""
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
                # Crossing implies flow > 0 strictly: cumulative = previous + flow,
                # with previous < 0 and cumulative >= 0. So this cannot divide by zero.
                return Decimal(index - 1) + (-previous / flow)
    return None


def solve_for_threshold(
    holds: object,
    low: Decimal,
    high: Decimal,
    *,
    rising: bool = True,
) -> Decimal | None:
    """The least demanding value in [low, high] at which a monotone claim holds.

    Root-finding answers "where does this equal the target". Most claims worth
    testing are inequalities -- pay back *within* three years -- and their
    objectives are step functions, so the target can be stepped straight over: a
    vintage can go from never paying back to paying back in four years with
    nothing in between. Asked for equality, the search finds nothing and reports
    the claim impossible while the top of the range satisfies it comfortably.

    Searching the predicate needs only monotonicity, which is what the levers
    have. The returned value always satisfies the claim, because the search only
    ever moves the satisfying bound inward.

    ``rising`` says which direction helps. Utilization, revenue yield and margin
    improve a claim as they increase; lead time makes it worse, so there the
    answer is the largest value that still works rather than the smallest.
    """
    assert callable(holds)
    better, worse = (high, low) if rising else (low, high)
    if holds(worse):
        # Even the least demanding end of the range clears it.
        return worse
    if not holds(better):
        return None
    for _ in range(MAX_ITERATIONS):
        if abs(better - worse) < CONVERGENCE_TOLERANCE:
            return better
        middle = (better + worse) / 2
        if holds(middle):
            better = middle
        else:
            worse = middle
    return better


def solve_for_root(
    evaluate: object,
    low: Decimal,
    high: Decimal,
) -> Decimal | None:
    """Find x in [low, high] where ``evaluate(x)`` is zero, by bisection.

    ``None`` when the endpoints do not bracket a sign change, meaning no value in
    the searched range satisfies the condition. That is a real finding: it says
    the claim cannot be met anywhere in the plausible range.

    Also ``None`` when the interval collapses onto a discontinuity rather than a
    crossing. Returning the midpoint of a jump would dress a value that satisfies
    nothing as the answer to "what would have to be true".
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

    # A sign change across an interval means a crossing only if the function is
    # continuous there. A jump changes sign too, and bisection narrows onto it
    # just as happily, so the interval collapsing is not on its own evidence that
    # a root was found. Measured against the scale the search started at, because
    # an absolute threshold cannot serve both a payback in years and a net present
    # value in billions.
    scale = max(abs(value_low), abs(value_high))
    threshold = scale * RESIDUAL_FRACTION

    for _ in range(MAX_ITERATIONS):
        middle = (low + high) / 2
        value_middle = evaluate(middle)
        if value_middle is None:
            return None
        if abs(value_middle) < CONVERGENCE_TOLERANCE:
            return middle
        if (high - low) < CONVERGENCE_TOLERANCE:
            return middle if abs(value_middle) <= threshold else None
        if value_low * value_middle < 0:
            high = middle
        else:
            low, value_low = middle, value_middle
    return None
