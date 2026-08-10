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
from functools import cached_property
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from capex_atlas.bundle.audit import AuditReport, audit_bundle
from capex_atlas.bundle.builder import build_analysis
from capex_atlas.bundle.charts import chart_data, vintage_cash_flow_spec
from capex_atlas.bundle.diff import BundleDiff, diff_bundles
from capex_atlas.bundle.io import read_bundle
from capex_atlas.bundle.model import AnalysisBundle
from capex_atlas.capital_vintages.solver import Lever, Target
from capex_atlas.obs import tracing
from capex_atlas.scenarios.model import ScenarioDefinition, ScenarioResult
from capex_atlas.scenarios.run import run_scenario
from capex_atlas.schemas.calculation import CalculationNode
from capex_atlas.schemas.charts import ChartSpec
from capex_atlas.schemas.decimals import format_compact, format_value
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.facts import FinancialFact
from capex_atlas.schemas.source import SourceKind, SourceReference
from capex_atlas.schemas.values import AnalyticalValue
from capex_atlas.viz.render import render

CARD_TITLES: Final = {
    "return on invested capital (operating basis)": "ROIC (operating basis)",
    "return on invested capital (excluding cash)": "ROIC (excluding cash)",
    "net operating profit after tax": "NOPAT",
}
"""Labels whose display form is not just the label capitalised.

Only the abbreviations earn an entry. Everything else takes a leading capital,
because a table of hand-written titles drifts from the labels it mirrors.
"""

CONCEPT_TITLES: Final = {
    "PaymentsToAcquirePropertyPlantAndEquipment": "Capital expenditure",
    "NetCashProvidedByUsedInOperatingActivities": "Cash from operations",
    "DepreciationDepletionAndAmortization": "Depreciation and amortization",
    "Depreciation": "Depreciation",
    "Revenues": "Revenue",
    "OperatingIncomeLoss": "Operating income",
    "Assets": "Total assets",
    "LiabilitiesCurrent": "Current liabilities",
    "CashAndCashEquivalentsAtCarryingValue": "Cash and equivalents",
    "MarketableSecuritiesCurrent": "Marketable securities",
    "FinanceLeasePrincipalPayments": "Finance lease principal",
}
"""Readable names for the XBRL tags a reader is likely to meet.

An unmapped tag falls back to the tag itself, which is ugly but never wrong.
"""

HEADLINE_RATIOS: Final = ("capex to depreciation", "capex intensity")
HEADLINE_LINEAGE: Final = "capex to depreciation"
"""The published value whose leaves are the two figures worth leading with."""


def display_title(label: str) -> str:
    """A card label as a reader should see it."""
    return CARD_TITLES.get(label) or label[:1].upper() + label[1:]


class MetricCard(BaseModel):
    """One headline figure, ready to render."""

    model_config = ConfigDict(frozen=True)

    label: str
    """The bundle's own label. The lookup key, so never rewritten for display."""
    title: str
    """What a reader sees. ``ROIC (operating basis)`` for the label above."""
    formatted: str
    """The exact figure: ``73,266,000,000.00 USD``. For tooltips and checking."""
    display: str
    """The scanning figure: ``$73.3B``. For the face of the card."""
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
    """One step in a value's lineage, with its depth for indenting.

    A step is either a calculation or a leaf fact read from a filing. Leaves
    carry ``concept`` and no ``formula``, which is how a renderer tells them
    apart: the tree bottoms out in things a company reported, and showing that
    is the whole point of the page.
    """

    model_config = ConfigDict(frozen=True)

    depth: int
    metric_id: str
    formula: str
    result: Decimal | None
    unit: str
    status: EvidenceStatus
    node_id: str
    concept: str | None = None
    """The XBRL tag, when this step is a reported fact rather than a calculation."""
    period_label: str | None = None

    @property
    def is_fact(self) -> bool:
        return self.concept is not None


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

    def headline(self) -> list[MetricCard]:
        """What the company did with its money, before any of the modelling.

        Two reported facts and the two ratios built from them. A reader arriving
        cold wants the spending itself first; every other published figure on the
        page is a calculation, so without this the lab never shows a single ●
        reported number despite being built to distinguish them.
        """
        facts = [
            self._fact_card(node)
            for node in self.lineage(HEADLINE_LINEAGE)
            if node.is_fact and node.result is not None
        ]
        ratios = [self.card(label) for label in HEADLINE_RATIOS]
        return [*facts, *[card for card in ratios if card is not None]]

    def overview(self) -> list[MetricCard]:
        """Every headline value as a renderable card."""
        return [self._card(value) for value in self.bundle.values]

    def card(self, label: str) -> MetricCard | None:
        value = self.bundle.value(label)
        return self._card(value) if value else None

    def _fact_card(self, node: ProvenanceNode) -> MetricCard:
        """A reported fact dressed as a card, so it sits beside derived ones."""
        concept = node.concept or node.metric_id
        return MetricCard(
            label=concept,
            title=CONCEPT_TITLES.get(concept, concept),
            formatted=format_value(node.result, node.unit),
            display=format_compact(node.result, node.unit),
            status=node.status,
            glyph=node.status.glyph,
            period_label=node.period_label,
            formula=None,
            source_count=1,
            assumption_ids=(),
        )

    def _card(self, value: AnalyticalValue) -> MetricCard:
        node = self.bundle.node(value.formula_node_id) if value.formula_node_id else None
        label = value.label or value.value_id
        return MetricCard(
            label=label,
            title=display_title(label),
            formatted=value.formatted,
            display=format_compact(value.value, value.unit),
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

    @cached_property
    def _facts_by_value_id(self) -> dict[str, FinancialFact]:
        """Leaf inputs, keyed the way a calculation node refers to them.

        A node's ``inputs`` are ``AnalyticalValue`` ids, and the leaves of every
        chain are facts read from a filing. The bundle stores the facts but not
        the wrapper values, so the id is recomputed here through the same
        constructor the metric layer used. Recomputing rather than storing keeps
        the bundle smaller and cannot drift: if ``from_fact`` ever changes, both
        sides change together.
        """
        return {AnalyticalValue.from_fact(fact).value_id: fact for fact in self.bundle.facts}

    def _walk(
        self, node_id: str, *, depth: int, seen: set[str], into: list[ProvenanceNode]
    ) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        node = self.bundle.node(node_id)
        if node is None:
            self._append_fact(node_id, depth=depth, into=into)
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
                period_label=node.period_label,
            )
        )
        for child in node.inputs:
            self._walk(child, depth=depth + 1, seen=seen, into=into)

    def _append_fact(self, value_id: str, *, depth: int, into: list[ProvenanceNode]) -> None:
        """Bottom out the tree in something a company reported.

        An unresolvable id is skipped rather than raised on. A tree missing a
        leaf is still an honest account of the rest; a page that dies because
        one input was pruned from the bundle is not.
        """
        fact = self._facts_by_value_id.get(value_id)
        if fact is None:
            return
        into.append(
            ProvenanceNode(
                depth=depth,
                metric_id=fact.metric_id,
                formula="",
                result=fact.value,
                unit=fact.unit,
                status=fact.status,
                node_id=value_id,
                concept=fact.xbrl_concept or fact.metric_id,
                period_label=fact.period.label if fact.period else None,
            )
        )

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

    # ----------------------------------------------------------------- charts

    def charts(self) -> tuple[ChartSpec, ...]:
        """The chart specifications this bundle carries."""
        return self.bundle.charts

    def scenario_figure(self, result: ScenarioResult) -> dict[str, Any]:
        """Render a freshly run scenario through the grammar the bundle uses.

        Exists so a page never builds a chart specification of its own; the
        front end asks for a figure and renders it.
        """
        spec = vintage_cash_flow_spec(self.bundle.entity_id)
        return render(spec, chart_data(spec, values=(), facts=(), scenario=result))

    def figure(self, data_ref: str, *, scenario_index: int = 0) -> dict[str, Any] | None:
        """Render one of the bundle's charts to a Plotly figure dictionary.

        Goes through the chart grammar rather than handing raw numbers to a
        plotting call, so each mark inherits the evidence status of the value it
        draws. A chart that renders a scenario the same way it renders a reported
        figure has undone the work every layer beneath it did.
        """
        spec = next((item for item in self.bundle.charts if item.data_ref == data_ref), None)
        if spec is None:
            return None
        scenario = (
            self.bundle.scenarios[scenario_index]
            if len(self.bundle.scenarios) > scenario_index
            else None
        )
        data = chart_data(
            spec, values=self.bundle.values, facts=self.bundle.facts, scenario=scenario
        )
        if not data or not data.get(spec.x_field):
            return None
        return render(spec, data)

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
