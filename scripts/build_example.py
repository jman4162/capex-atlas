"""Rebuild the worked example under ``examples/``.

Built from the hash-pinned fixture rather than from a live SEC call, so anyone
can regenerate it offline and get the same bytes. CI rebuilds it and compares, so
the example cannot drift away from the code that produced it.

    uv run python scripts/build_example.py
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from capex_atlas.bundle.builder import FactScope, build_analysis
from capex_atlas.bundle.io import write_bundle
from capex_atlas.capital_vintages.model import AssetClassParameters
from capex_atlas.capital_vintages.solver import Lever, Target
from capex_atlas.scenarios.model import ScenarioDefinition
from capex_atlas.scenarios.run import run_scenario
from capex_atlas.schemas.capital import CapitalCategory
from capex_atlas.schemas.source import SourceKind, SourceReference

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "googl_companyfacts_trimmed.json"
TARGET = REPO_ROOT / "examples" / "googl-2025fy"

ENTITY = "GOOGL"
PERIOD = "2025FY"
SOURCE_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json"


def illustrative_scenario() -> ScenarioDefinition:
    """A scenario whose only purpose is to show the machinery.

    The parameters are round numbers chosen to be legible, not estimates of
    anyone's economics. Every figure it produces is marked as a scenario, which
    is the correct reading of numbers nobody disclosed.
    """
    return ScenarioDefinition(
        scenario_id="illustrative-server-vintage",
        name="Illustrative server vintage",
        description=(
            "A round-numbers vintage used to demonstrate the engine. The parameters are "
            "chosen to be legible, not to estimate any company's returns, and every "
            "figure it produces is marked as a scenario. Not an estimate."
        ),
        asset_classes=(
            AssetClassParameters(
                asset_class=CapitalCategory.SERVERS,
                # Ten billion dollars, the scale a hyperscaler actually commits to
                # one vintage. Return, payback and the sensitivity ordering do not
                # depend on it, but a net present value of $1.2k sitting under
                # $91.4B of capex invites the reader to mistrust the units.
                spend=Decimal("1e10"),
                lead_time_years=Decimal(0),
                # The one parameter here taken from a filing rather than chosen.
                useful_life_years=Decimal(6),
                utilization_ramp=(Decimal("0.40"), Decimal("0.70"), Decimal("0.85")),
                revenue_yield=Decimal("0.75"),
                operating_margin=Decimal("0.55"),
                maintenance_rate=Decimal("0.08"),
            ),
        ),
        tax_rate=Decimal("0.21"),
        discount_rate=Decimal("0.09"),
        horizon_years=8,
        assumption_ids=(
            "useful_life.servers_and_network.googl",
            "tax.us_federal_statutory_rate",
            "discount.required_return",
        ),
    )


def build() -> Path:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    scenario = run_scenario(
        illustrative_scenario(),
        requirements=(
            (
                Lever.UTILIZATION,
                Target.PAYBACK_YEARS,
                Decimal(3),
                Decimal("0.05"),
                Decimal(1),
            ),
        ),
        sensitivities={
            Lever.REVENUE_YIELD: (Decimal("0.25"), Decimal("0.60")),
            Lever.OPERATING_MARGIN: (Decimal("0.45"), Decimal("0.65")),
            Lever.LEAD_TIME: (Decimal(0), Decimal(3)),
        },
    )
    bundle = build_analysis(
        payload,
        entity_id=ENTITY,
        period_label=PERIOD,
        source=SourceReference(kind=SourceKind.SEC_FILING, url=SOURCE_URL),
        # 'annual' rather than 'period': with only the analyzed period the charts
        # degenerate to a single point. Quarterly facts stay out because no chart
        # plots them and they would triple the file.
        facts_scope=FactScope.ANNUAL,
        scenarios=(scenario,),
        command="python scripts/build_example.py",
    )
    return write_bundle(bundle, TARGET)


if __name__ == "__main__":
    written = build()
    size = written.stat().st_size / 1024
    print(f"wrote {written.relative_to(REPO_ROOT)} ({size:.0f} KB)")
