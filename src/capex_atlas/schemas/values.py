"""The unit of currency between calculations.

Every number that reaches a chart, a report or the CLI is an ``AnalyticalValue``,
never a bare ``Decimal``. That is what makes it impossible to render a figure
without also knowing its status, its formula and its sources.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.facts import FinancialFact
from capex_atlas.schemas.hashing import stable_id
from capex_atlas.schemas.period import FiscalPeriod


class AnalyticalValue(BaseModel):
    """A number plus its epistemic pedigree."""

    model_config = ConfigDict(frozen=True)

    value_id: str
    value: Decimal | None
    unit: str
    status: EvidenceStatus
    period: FiscalPeriod | None = None

    label: str | None = None
    formula_node_id: str | None = None
    source_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    confidence: float | None = None

    @classmethod
    def from_fact(cls, fact: FinancialFact, label: str | None = None) -> AnalyticalValue:
        """Lift a reported fact into the calculation layer.

        The id folds in the amount and the source, unlike ``fact_id``, which is
        identity-only so the reconciliation layer can spot a restatement. Two
        contradictory figures for the same concept and period must be distinct
        calculation inputs, or a graph built from both would silently treat them
        as one.
        """
        return cls(
            value_id=stable_id("val", fact.fact_id, fact.value, fact.source.source_id),
            value=fact.value,
            unit=fact.unit,
            status=fact.status,
            period=fact.period,
            label=label or fact.metric_id,
            source_ids=(fact.source.source_id,),
            confidence=fact.confidence,
        )

    @property
    def is_known(self) -> bool:
        return self.value is not None and self.status is not EvidenceStatus.UNRESOLVED

    def __str__(self) -> str:
        shown = "—" if self.value is None else f"{self.value:,f}"
        return f"{self.status.glyph} {shown} {self.unit}"
