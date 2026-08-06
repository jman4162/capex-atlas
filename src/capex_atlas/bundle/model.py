"""The analysis bundle.

The central artifact. Streamlit, notebooks, the CLI and any published article all
consume bundles rather than recomputing, which is what stops a saved analysis
from changing when a new filing lands. A conclusion written against a bundle
stays reproducible, and when it does change, the diff says why.

A bundle carries its own disclaimer. The text is not decoration: these files are
meant to be handed around, and a set of figures that arrives without the
conditions attached is the failure mode this package exists to avoid.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from functools import cached_property
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from capex_atlas.accounting.reconciliation import ReconciliationReport
from capex_atlas.assumptions.models import Assumption
from capex_atlas.disclaimer import SHORT
from capex_atlas.scenarios.model import ScenarioResult
from capex_atlas.schemas.calculation import CalculationNode
from capex_atlas.schemas.charts import ChartSpec
from capex_atlas.schemas.claims import ManagementClaim
from capex_atlas.schemas.facts import FinancialFact
from capex_atlas.schemas.source import SourceReference
from capex_atlas.schemas.values import AnalyticalValue

SCHEMA_VERSION = "1"


class BundleProvenance(BaseModel):
    """Everything about *when* and *by what* the bundle was made.

    Segregated from the analysis so that two runs over the same inputs differ
    here and nowhere else, which is what makes the reproducibility check a
    byte-level comparison rather than a judgement call.
    """

    model_config = ConfigDict(frozen=True)

    created_at: datetime
    package_version: str
    schema_version: str = SCHEMA_VERSION
    command: str | None = None


class AnalysisBundle(BaseModel):
    """A frozen, self-describing analysis."""

    model_config = ConfigDict(frozen=True, ignored_types=(cached_property,))

    entity_id: str
    period_label: str
    template: str = "default"

    extra_sources: tuple[SourceReference, ...] = ()
    """Citations not already carried by a fact, such as a transcript behind a claim.

    Fact citations are *not* repeated here. Each fact already embeds its own, and
    storing them twice made a third of a bundle redundant bytes.
    """

    facts: tuple[FinancialFact, ...] = ()
    values: tuple[AnalyticalValue, ...] = ()
    """Headline results. Intermediate steps live in ``calculations``."""

    calculations: tuple[CalculationNode, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    claims: tuple[ManagementClaim, ...] = ()
    charts: tuple[ChartSpec, ...] = ()
    scenarios: tuple[ScenarioResult, ...] = ()
    validation: ReconciliationReport | None = None

    disclaimer: str = SHORT
    notes: dict[str, Any] = Field(default_factory=dict)
    provenance: BundleProvenance | None = None

    @cached_property
    def sources(self) -> tuple[SourceReference, ...]:
        """Every citation the bundle can resolve, in id order.

        Derived from the facts rather than stored beside them, so a bundle
        cannot end up with a source list that disagrees with the facts it holds.
        """
        seen: dict[str, SourceReference] = {}
        for fact in self.facts:
            seen.setdefault(fact.source.source_id, fact.source)
        for claim in self.claims:
            seen.setdefault(claim.evidence.source_id, claim.evidence)
        for source in self.extra_sources:
            seen.setdefault(source.source_id, source)
        return tuple(seen[key] for key in sorted(seen))

    def value(self, label: str) -> AnalyticalValue | None:
        for item in self.values:
            if item.label == label:
                return item
        return None

    def node(self, node_id: str) -> CalculationNode | None:
        for item in self.calculations:
            if item.node_id == node_id:
                return item
        return None

    def source(self, source_id: str) -> SourceReference | None:
        for item in self.sources:
            if item.source_id == source_id:
                return item
        return None

    def assumption(self, assumption_id: str) -> Assumption | None:
        for item in self.assumptions:
            if item.assumption_id == assumption_id:
                return item
        return None

    @property
    def headline(self) -> dict[str, Decimal | None]:
        return {item.label or item.value_id: item.value for item in self.values}
