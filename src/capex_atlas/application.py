"""The service layer.

Everything a front end needs, and nothing a front end should do itself. Pages
call these methods and render what comes back; if a Streamlit file starts doing
arithmetic, the front end has stopped being replaceable and the calculation has
escaped the provenance kernel.

Loading is separated from analysis on purpose. Reading a stored bundle is cheap,
deterministic and offline; building one may reach the network. A page that only
displays should never trip the second.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from capex_atlas.bundle.audit import AuditReport, audit_bundle
from capex_atlas.bundle.builder import build_analysis
from capex_atlas.bundle.diff import BundleDiff, diff_bundles
from capex_atlas.bundle.io import read_bundle
from capex_atlas.bundle.model import AnalysisBundle
from capex_atlas.capital_vintages.solver import Lever, Target
from capex_atlas.obs import tracing
from capex_atlas.scenarios.model import ScenarioDefinition, ScenarioResult
from capex_atlas.scenarios.run import run_scenario
from capex_atlas.schemas.calculation import CalculationNode
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.source import SourceKind, SourceReference
from capex_atlas.schemas.values import AnalyticalValue


class MetricCard(BaseModel):
    """One headline figure, ready to render."""

    model_config = ConfigDict(frozen=True)

    label: str
    formatted: str
    status: EvidenceStatus
    glyph: str
    period_label: str | None
    formula: str | None
    source_count: int
    assumption_ids: tuple[str, ...]

    @property
    def is_known(self) -> bool:
        return self.status is not EvidenceStatus.UNRESOLVED


class ProvenanceNode(BaseModel):
    """One step in a value's lineage, with its depth for indenting."""

    model_config = ConfigDict(frozen=True)

    depth: int
    metric_id: str
    formula: str
    result: Decimal | None
    unit: str
    status: EvidenceStatus
    node_id: str


class SeriesPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    period_label: str
    value: Decimal
    status: EvidenceStatus


class AtlasApplication:
    """What the Streamlit lab, a notebook or the CLI all talk to."""

    def __init__(self, bundle: AnalysisBundle) -> None:
        self.bundle = bundle

    # ---------------------------------------------------------------- loading

    @classmethod
    def from_path(cls, path: Path) -> AtlasApplication:
        """Open a stored bundle. Offline and deterministic."""
        return cls(read_bundle(path))

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        entity_id: str,
        period_label: str,
        source_url: str,
    ) -> AtlasApplication:
        """Build an analysis from a Company Facts payload."""
        with tracing.span(
            "capex_atlas.bundle.publish",
            **{
                "capex_atlas.company.ticker": entity_id,
                "capex_atlas.fiscal.period": period_label,
            },
        ):
            bundle = build_analysis(
                payload,
                entity_id=entity_id,
                period_label=period_label,
                source=SourceReference(kind=SourceKind.SEC_FILING, url=source_url),
            )
        return cls(bundle)

    @classmethod
    def from_json_file(cls, path: Path, *, entity_id: str, period_label: str) -> AtlasApplication:
        """Build from a Company Facts file already on disk."""
        return cls.from_payload(
            json.loads(path.read_text(encoding="utf-8")),
            entity_id=entity_id,
            period_label=period_label,
            source_url=path.as_uri(),
        )

    # --------------------------------------------------------------- overview

    def overview(self) -> list[MetricCard]:
        """Every headline value as a renderable card."""
        return [self._card(value) for value in self.bundle.values]

    def card(self, label: str) -> MetricCard | None:
        value = self.bundle.value(label)
        return self._card(value) if value else None

    def _card(self, value: AnalyticalValue) -> MetricCard:
        node = self.bundle.node(value.formula_node_id) if value.formula_node_id else None
        return MetricCard(
            label=value.label or value.value_id,
            formatted=value.formatted,
            status=value.status,
            glyph=value.status.glyph,
            period_label=value.period.label if value.period else None,
            formula=node.formula if node else None,
            source_count=len(value.source_ids),
            assumption_ids=value.assumption_ids,
        )

    def evidence_mix(self) -> dict[EvidenceStatus, int]:
        """How many published figures sit at each status.

        Lets a reader weigh an analysis at a glance: a page of scenarios and a
        page of reported facts should not look alike.
        """
        counts: dict[EvidenceStatus, int] = {}
        for value in self.bundle.values:
            counts[value.status] = counts.get(value.status, 0) + 1
        return counts

    # ------------------------------------------------------------- provenance

    def lineage(self, label: str) -> list[ProvenanceNode]:
        """Walk a value back through the calculations that produced it."""
        value = self.bundle.value(label)
        if value is None or value.formula_node_id is None:
            return []
        collected: list[ProvenanceNode] = []
        self._walk(value.formula_node_id, depth=0, seen=set(), into=collected)
        return collected

    def _walk(
        self, node_id: str, *, depth: int, seen: set[str], into: list[ProvenanceNode]
    ) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        node = self.bundle.node(node_id)
        if node is None:
            return
        into.append(
            ProvenanceNode(
                depth=depth,
                metric_id=node.metric_id,
                formula=node.formula,
                result=node.result,
                unit=node.unit,
                status=node.status,
                node_id=node.node_id,
            )
        )
        for child in node.inputs:
            self._walk(child, depth=depth + 1, seen=seen, into=into)

    def sources_for(self, label: str) -> list[SourceReference]:
        """The filings a value rests on."""
        value = self.bundle.value(label)
        if value is None:
            return []
        found = [self.bundle.source(source_id) for source_id in value.source_ids]
        return [source for source in found if source is not None]

    def calculation(self, node_id: str) -> CalculationNode | None:
        return self.bundle.node(node_id)

    # ----------------------------------------------------------------- series

    def series(self, concept: str, *, kind: str | None = None) -> list[SeriesPoint]:
        """A concept's history, for charting.

        Filtering by period kind matters: mixing quarters with year-to-date
        figures on one axis produces a sawtooth that looks like a business
        collapsing and recovering four times a year.
        """
        points = [
            SeriesPoint(period_label=fact.period.label, value=fact.value, status=fact.status)
            for fact in self.bundle.facts
            if fact.metric_id == concept and (kind is None or fact.period.kind.value == kind)
        ]
        return sorted(points, key=lambda point: point.period_label)

    def concepts(self) -> list[str]:
        return sorted({fact.metric_id for fact in self.bundle.facts})

    # -------------------------------------------------------------- scenarios

    def run_scenario(
        self,
        definition: ScenarioDefinition,
        *,
        requirements: tuple[tuple[Lever, Target, Decimal, Decimal, Decimal], ...] = (),
        sensitivities: dict[Lever, tuple[Decimal, Decimal]] | None = None,
    ) -> ScenarioResult:
        """Evaluate a scenario. Never called on a widget rerun; see the app."""
        with tracing.span(
            "capex_atlas.scenario.run",
            **{
                "capex_atlas.scenario.id": definition.scenario_id,
                "capex_atlas.company.ticker": self.bundle.entity_id,
                "capex_atlas.scenario.horizon_years": definition.horizon_years,
            },
        ):
            return run_scenario(definition, requirements=requirements, sensitivities=sensitivities)

    # ------------------------------------------------------------ integrity

    def audit(self) -> AuditReport:
        return audit_bundle(self.bundle)

    def compare(self, other: AnalysisBundle) -> BundleDiff:
        return diff_bundles(self.bundle, other)

    @property
    def validation_summary(self) -> str:
        report = self.bundle.validation
        if report is None:
            return "no reconciliation was run"
        return f"{report.verified_count} accounting checks verified, {len(report.failures)} failed"
