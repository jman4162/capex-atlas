"""Running a scenario and packaging the result."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from capex_atlas.capital_vintages.engine import build_schedule, summarize
from capex_atlas.capital_vintages.solver import Lever, Target, required_for, tornado
from capex_atlas.scenarios.model import (
    RequirementSummary,
    ScenarioDefinition,
    ScenarioResult,
    SensitivitySummary,
)


def run_scenario(
    definition: ScenarioDefinition,
    *,
    requirements: Sequence[tuple[Lever, Target, Decimal, Decimal, Decimal]] = (),
    sensitivities: Mapping[Lever, tuple[Decimal, Decimal]] | None = None,
) -> ScenarioResult:
    """Evaluate *definition*, optionally solving conditions and ranking levers.

    Each requirement is ``(lever, target, target_value, search_low, search_high)``.
    The search bounds are the caller's statement of what counts as plausible, and
    a requirement that finds nothing in that range is kept rather than dropped:
    "no value here works" is the finding.
    """
    schedule = build_schedule(
        definition.asset_classes,
        tax_rate=definition.tax_rate,
        horizon_years=definition.horizon_years,
    )
    summary = summarize(schedule, discount_rate=definition.discount_rate)

    solved = []
    for lever, target, target_value, low, high in requirements:
        result = required_for(
            definition.asset_classes,
            lever=lever,
            target=target,
            target_value=target_value,
            tax_rate=definition.tax_rate,
            discount_rate=definition.discount_rate,
            horizon_years=definition.horizon_years,
            search_low=low,
            search_high=high,
        )
        solved.append(
            RequirementSummary(
                lever=result.lever.value,
                target=result.target.value,
                target_value=result.target_value,
                required=result.required,
                searched_low=result.searched_low,
                searched_high=result.searched_high,
                description=result.describe(),
            )
        )

    bands = []
    if sensitivities:
        for band in tornado(
            definition.asset_classes,
            levers=dict(sensitivities),
            tax_rate=definition.tax_rate,
            discount_rate=definition.discount_rate,
            horizon_years=definition.horizon_years,
        ):
            bands.append(
                SensitivitySummary(
                    lever=band.lever.value,
                    low_input=band.low_input,
                    high_input=band.high_input,
                    swing=band.swing,
                )
            )

    return ScenarioResult(
        definition=definition,
        npv=summary["npv"],
        irr=summary["irr"],
        payback=summary["payback"],
        schedule=schedule,
        requirements=tuple(solved),
        sensitivities=tuple(bands),
    )
