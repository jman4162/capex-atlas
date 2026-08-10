"""Running the vintage model backwards.

The forward question, "what return does this capital earn", cannot be answered
from public accounts: the inputs it needs are exactly the ones companies do not
disclose. The inverse question can be answered, and is more useful anyway.

Given a management claim, solve for the utilization, revenue yield, margin or
delay at which the claim would hold, then let the reader judge whether that
number is plausible. The output is a condition, not a verdict, which is the only
honest thing public data supports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from capex_atlas.capital_vintages.engine import build_schedule
from capex_atlas.capital_vintages.model import AssetClassParameters
from capex_atlas.numerics import (
    internal_rate_of_return,
    net_present_value,
    payback_period,
    solve_for_root,
)
from capex_atlas.schemas.decimals import format_compact
from capex_atlas.schemas.evidence import EvidenceStatus


class Lever(StrEnum):
    """The parameter being solved for."""

    UTILIZATION = "utilization"
    REVENUE_YIELD = "revenue_yield"
    OPERATING_MARGIN = "operating_margin"
    LEAD_TIME = "lead_time_years"


class Target(StrEnum):
    """The claim being tested."""

    PAYBACK_YEARS = "payback_years"
    IRR = "irr"
    NPV_BREAKEVEN = "npv_breakeven"


LEVER_TITLES: Final = {
    Lever.UTILIZATION: "utilization",
    Lever.REVENUE_YIELD: "revenue yield",
    Lever.OPERATING_MARGIN: "operating margin",
    Lever.LEAD_TIME: "lead time",
}
"""Readable names. The enum values are identifiers and read as such in a sentence."""

LEVER_UNITS: Final = {
    Lever.UTILIZATION: "percent",
    Lever.REVENUE_YIELD: "ratio",
    Lever.OPERATING_MARGIN: "percent",
    Lever.LEAD_TIME: "years",
}
"""Utilization and margin are shares of a whole. Revenue yield is revenue per unit
of capital, which is a rate rather than a share, so it stays a bare ratio."""

TARGET_TITLES: Final = {
    Target.PAYBACK_YEARS: "payback",
    Target.IRR: "IRR",
    Target.NPV_BREAKEVEN: "NPV breakeven",
}

TARGET_UNITS: Final = {
    Target.PAYBACK_YEARS: "years",
    Target.IRR: "percent",
    Target.NPV_BREAKEVEN: "USD",
}


@dataclass(frozen=True)
class RequirementResult:
    """What a lever must reach for a claim to hold."""

    lever: Lever
    target: Target
    target_value: Decimal
    required: Decimal | None
    searched_low: Decimal
    searched_high: Decimal
    status: EvidenceStatus

    @property
    def achievable(self) -> bool:
        """Whether any value in the searched range satisfies the claim."""
        return self.required is not None

    def describe(self) -> str:
        lever = LEVER_TITLES[self.lever]
        lever_unit = LEVER_UNITS[self.lever]
        wanted = format_compact(self.target_value, TARGET_UNITS[self.target])
        claim = f"{TARGET_TITLES[self.target]} of {wanted}"
        if self.required is None:
            low = format_compact(self.searched_low, lever_unit)
            high = format_compact(self.searched_high, lever_unit)
            return (
                f"No {lever} between {low} and {high} reaches {claim}. On these assumptions the "
                "claim cannot hold anywhere in the plausible range."
            )
        return f"A {lever} of {format_compact(self.required, lever_unit)} is required for {claim}."


def _with_lever(
    parameters: Sequence[AssetClassParameters], lever: Lever, value: Decimal
) -> list[AssetClassParameters]:
    """Copy the parameters with *lever* set to *value* across every asset class."""
    updated = []
    for asset in parameters:
        if lever is Lever.UTILIZATION:
            ramp = tuple(value for _ in asset.utilization_ramp) or (value,)
            updated.append(asset.model_copy(update={"utilization_ramp": ramp}))
        elif lever is Lever.REVENUE_YIELD:
            updated.append(asset.model_copy(update={"revenue_yield": value}))
        elif lever is Lever.OPERATING_MARGIN:
            updated.append(asset.model_copy(update={"operating_margin": value}))
        else:
            updated.append(asset.model_copy(update={"lead_time_years": value}))
    return updated


def required_for(
    parameters: Sequence[AssetClassParameters],
    *,
    lever: Lever,
    target: Target,
    target_value: Decimal,
    tax_rate: Decimal,
    discount_rate: Decimal,
    horizon_years: int,
    search_low: Decimal,
    search_high: Decimal,
) -> RequirementResult:
    """Solve for the *lever* value at which *target* is met.

    The search bounds are the caller's statement of what counts as plausible.
    Returning nothing is a real answer: it means the claim fails across that
    whole range, which is more informative than a number would have been.
    """

    def shortfall(candidate: Decimal) -> Decimal | None:
        schedule = build_schedule(
            _with_lever(parameters, lever, candidate),
            tax_rate=tax_rate,
            horizon_years=horizon_years,
        )
        flows = schedule.cash_flows
        if target is Target.NPV_BREAKEVEN:
            return net_present_value(flows, discount_rate) - target_value
        if target is Target.IRR:
            rate = internal_rate_of_return(flows)
            return None if rate is None else rate - target_value
        years = payback_period(flows)
        if years is None:
            # Never pays back within the horizon, so it misses the target by at
            # least the whole horizon. Signed so bisection can still work.
            return Decimal(horizon_years) - target_value
        return target_value - years

    required = solve_for_root(shortfall, search_low, search_high)
    weakest = EvidenceStatus.weakest(
        EvidenceStatus.SCENARIO, *(asset.status for asset in parameters)
    )
    return RequirementResult(
        lever=lever,
        target=target,
        target_value=target_value,
        required=required,
        searched_low=search_low,
        searched_high=search_high,
        status=weakest,
    )


@dataclass(frozen=True)
class SensitivityBand:
    """How far one lever moves an outcome across its plausible range."""

    lever: Lever
    low_input: Decimal
    high_input: Decimal
    low_output: Decimal | None
    high_output: Decimal | None

    @property
    def swing(self) -> Decimal | None:
        if self.low_output is None or self.high_output is None:
            return None
        return abs(self.high_output - self.low_output)


def tornado(
    parameters: Sequence[AssetClassParameters],
    *,
    levers: dict[Lever, tuple[Decimal, Decimal]],
    tax_rate: Decimal,
    discount_rate: Decimal,
    horizon_years: int,
) -> list[SensitivityBand]:
    """Rank levers by how much they move net present value.

    The ordering is the useful output. It says which assumption a conclusion
    actually rests on, and therefore which one a sceptical reader should attack
    first.
    """
    bands: list[SensitivityBand] = []
    for lever, (low, high) in levers.items():
        outputs = []
        for candidate in (low, high):
            schedule = build_schedule(
                _with_lever(parameters, lever, candidate),
                tax_rate=tax_rate,
                horizon_years=horizon_years,
            )
            outputs.append(net_present_value(schedule.cash_flows, discount_rate))
        bands.append(
            SensitivityBand(
                lever=lever,
                low_input=low,
                high_input=high,
                low_output=outputs[0],
                high_output=outputs[1],
            )
        )
    bands.sort(key=lambda band: band.swing or Decimal(0), reverse=True)
    return bands
