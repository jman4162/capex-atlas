"""Invariants the what-must-be-true solver has to hold for any inputs.

Example-based tests found the payback solver reporting 67.3% utilization for a
claim that no utilization satisfies, because the one test covering that path
asserted the wrong expectation and passed. These state the property instead of a
case, so a search over the input space has to break it.

Two invariants, and they are the whole contract:

- **Soundness.** If the solver returns a value, the claim holds at that value.
  Anything else publishes a number that satisfies nothing.
- **Completeness.** If it refuses, no value in the bracket satisfies the claim.
  A refusal is presented to the reader as "cannot hold anywhere in the plausible
  range", which is a strong statement to make wrongly.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from capex_atlas.capital_vintages.engine import build_schedule
from capex_atlas.capital_vintages.model import AssetClassParameters
from capex_atlas.capital_vintages.solver import Lever, Target, required_for
from capex_atlas.numerics import payback_period
from capex_atlas.schemas.capital import CapitalCategory

TAX = Decimal("0.21")
DISCOUNT = Decimal("0.09")
HORIZON = 8
LOW = Decimal("0.05")
HIGH = Decimal(1)
SCAN_STEPS = 40
TOLERANCE = Decimal("0.01")

# Bisection over a schedule build is not cheap, and each example runs one solve
# plus a scan of the bracket.
SLOW = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def money(places: int = 2) -> st.SearchStrategy[Decimal]:
    return st.decimals(min_value=Decimal("0.05"), max_value=Decimal("0.95"), places=places)


def asset(revenue_yield: Decimal, margin: Decimal, life: int) -> AssetClassParameters:
    return AssetClassParameters(
        asset_class=CapitalCategory.SERVERS,
        spend=Decimal(1000),
        lead_time_years=Decimal(0),
        useful_life_years=Decimal(life),
        utilization_ramp=(Decimal("0.5"),),
        revenue_yield=revenue_yield,
        operating_margin=margin,
    )


def payback_at(base: AssetClassParameters, utilization: Decimal) -> Decimal | None:
    tuned = base.model_copy(update={"utilization_ramp": (utilization,)})
    schedule = build_schedule([tuned], tax_rate=TAX, horizon_years=HORIZON)
    return payback_period(schedule.cash_flows)


def solve(base: AssetClassParameters, target: Decimal):  # type: ignore[no-untyped-def]
    return required_for(
        [base],
        lever=Lever.UTILIZATION,
        target=Target.PAYBACK_YEARS,
        target_value=target,
        tax_rate=TAX,
        discount_rate=DISCOUNT,
        horizon_years=HORIZON,
        search_low=LOW,
        search_high=HIGH,
    )


def scan(base: AssetClassParameters) -> list[tuple[Decimal, Decimal | None]]:
    step = (HIGH - LOW) / SCAN_STEPS
    points = [LOW + step * index for index in range(SCAN_STEPS + 1)]
    return [(point, payback_at(base, point)) for point in points]


@SLOW
@given(revenue_yield=money(), margin=money(), life=st.integers(3, 10), target=st.integers(2, 8))
def test_a_returned_utilization_actually_meets_the_claim(
    revenue_yield: Decimal, margin: Decimal, life: int, target: int
) -> None:
    base = asset(revenue_yield, margin, life)
    result = solve(base, Decimal(target))
    if result.required is None:
        return
    achieved = payback_at(base, result.required)
    assert achieved is not None, (
        f"solver returned {result.required} but the vintage never pays back there"
    )
    assert achieved <= Decimal(target) + TOLERANCE, (
        f"solver returned {result.required} for a {target}-year payback; it gives {achieved}"
    )


@SLOW
@given(revenue_yield=money(), margin=money(), life=st.integers(3, 10), target=st.integers(2, 8))
def test_a_refusal_means_nothing_in_the_bracket_works(
    revenue_yield: Decimal, margin: Decimal, life: int, target: int
) -> None:
    base = asset(revenue_yield, margin, life)
    result = solve(base, Decimal(target))
    if result.required is not None:
        return
    achievable = [
        (point, years)
        for point, years in scan(base)
        if years is not None and years <= Decimal(target)
    ]
    assert not achievable, (
        f"solver said no utilization reaches a {target}-year payback, but "
        f"{achievable[0][0]} reaches {achievable[0][1]}"
    )


@SLOW
@given(revenue_yield=money(), margin=money(), life=st.integers(3, 10))
def test_payback_never_improves_as_utilization_falls(
    revenue_yield: Decimal, margin: Decimal, life: int
) -> None:
    """The monotonicity bisection depends on. If it broke, a single crossing
    would not be guaranteed and the search would be unsound for a deeper
    reason than the sign of one branch."""
    base = asset(revenue_yield, margin, life)
    defined = [(point, years) for point, years in scan(base) if years is not None]
    for (_, faster), (_, slower) in pairwise(defined):
        assert slower <= faster + TOLERANCE, "payback rose as utilization rose"
