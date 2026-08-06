"""Named scenarios and their results.

A scenario is a set of assumptions with a name attached. Naming matters more than
it sounds: "Management Case" and "Utilization Delay" are arguments, and a reader
comparing them is comparing arguments rather than being handed one answer.

Results carry the same evidence status as anything else, which for a scenario is
always the weakest one. That is the correct reading of a what-if and the reason
these live in the bundle rather than being rendered and forgotten.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from capex_atlas.capital_vintages.model import AssetClassParameters, VintageSchedule
from capex_atlas.schemas.calculation import CalculationNode
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.values import AnalyticalValue


class ScenarioDefinition(BaseModel):
    """Everything needed to reproduce a scenario run."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    name: str
    description: str = ""
    asset_classes: tuple[AssetClassParameters, ...]
    tax_rate: Decimal
    discount_rate: Decimal
    horizon_years: int
    assumption_ids: tuple[str, ...] = ()
    """Registry entries the parameters came from, so the audit can resolve them."""


class RequirementSummary(BaseModel):
    """A solved "what must be true" condition, flattened for serialization."""

    model_config = ConfigDict(frozen=True)

    lever: str
    target: str
    target_value: Decimal
    required: Decimal | None
    searched_low: Decimal
    searched_high: Decimal
    description: str

    @property
    def achievable(self) -> bool:
        return self.required is not None


class SensitivitySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    lever: str
    low_input: Decimal
    high_input: Decimal
    swing: Decimal | None


class ScenarioResult(BaseModel):
    """A scenario run, frozen alongside the analysis that produced it."""

    model_config = ConfigDict(frozen=True)

    definition: ScenarioDefinition
    npv: AnalyticalValue
    irr: AnalyticalValue
    payback: AnalyticalValue
    schedule: VintageSchedule
    calculations: tuple[CalculationNode, ...] = ()
    """Nodes from this run, so the audit can trace the scenario's own figures."""

    requirements: tuple[RequirementSummary, ...] = ()
    sensitivities: tuple[SensitivitySummary, ...] = Field(default_factory=tuple)

    @property
    def status(self) -> EvidenceStatus:
        return EvidenceStatus.weakest(self.npv.status, self.irr.status, self.payback.status)

    @property
    def values(self) -> tuple[AnalyticalValue, ...]:
        """The scenario's headline figures, for the audit to walk."""
        return (self.npv, self.irr, self.payback)
