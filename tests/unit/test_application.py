from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from capex_atlas.application import AtlasApplication
from capex_atlas.bundle.io import write_bundle
from capex_atlas.capital_vintages.model import AssetClassParameters
from capex_atlas.capital_vintages.solver import Lever, Target
from capex_atlas.scenarios.model import ScenarioDefinition
from capex_atlas.schemas.capital import CapitalCategory
from capex_atlas.schemas.evidence import EvidenceStatus

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "googl_companyfacts_trimmed.json"


@pytest.fixture(scope="module")
def app() -> AtlasApplication:
    return AtlasApplication.from_payload(
        json.loads(FIXTURE.read_text()),
        entity_id="GOOGL",
        period_label="2025FY",
        source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json",
    )


class TestOverview:
    def test_every_value_becomes_a_card(self, app: AtlasApplication):
        cards = app.overview()
        assert len(cards) == len(app.bundle.values)
        assert all(card.glyph for card in cards)

    def test_a_card_carries_its_formula(self, app: AtlasApplication):
        card = app.card("free cash flow (reported basis)")
        assert card is not None
        assert card.formula is not None
        assert "cash from operations" in card.formula

    def test_an_unresolved_card_says_so(self, app: AtlasApplication):
        card = app.card("free cash flow (standardized)")
        assert card is not None
        assert not card.is_known
        assert card.status is EvidenceStatus.UNRESOLVED

    def test_evidence_mix_separates_measured_from_assumed(self, app: AtlasApplication):
        mix = app.evidence_mix()
        assert mix[EvidenceStatus.DERIVED] > 0
        assert mix[EvidenceStatus.ESTIMATED] > 0

    def test_an_unknown_label_returns_nothing(self, app: AtlasApplication):
        assert app.card("no such metric") is None


class TestProvenance:
    def test_lineage_walks_back_to_the_inputs(self, app: AtlasApplication):
        lineage = app.lineage("return on invested capital (operating basis)")
        assert len(lineage) > 1
        assert lineage[0].depth == 0
        assert any(node.depth > 0 for node in lineage)

    def test_lineage_of_an_unknown_label_is_empty(self, app: AtlasApplication):
        assert app.lineage("no such metric") == []

    def test_sources_resolve_to_filings(self, app: AtlasApplication):
        sources = app.sources_for("free cash flow (reported basis)")
        assert sources
        assert all(source.accession for source in sources)

    def test_lineage_terminates_on_a_cycle(self, app: AtlasApplication):
        # Defensive: a malformed graph must not hang the interface.
        lineage = app.lineage("free cash flow (reported basis)")
        node_ids = [node.node_id for node in lineage]
        assert len(node_ids) == len(set(node_ids))


class TestSeries:
    def test_a_concept_history_is_ordered(self, app: AtlasApplication):
        points = app.series("PaymentsToAcquirePropertyPlantAndEquipment", kind="FY")
        labels = [point.period_label for point in points]
        assert labels == sorted(labels)
        assert len(points) >= 3

    def test_filtering_by_period_kind_avoids_mixing_bases(self, app: AtlasApplication):
        # Quarters and year-to-date figures on one axis look like a business
        # collapsing four times a year.
        annual = app.series("PaymentsToAcquirePropertyPlantAndEquipment", kind="FY")
        everything = app.series("PaymentsToAcquirePropertyPlantAndEquipment")
        assert len(annual) < len(everything)

    def test_concepts_are_listed(self, app: AtlasApplication):
        assert "Assets" in app.concepts()


class TestIntegrity:
    def test_the_bundle_audits_clean(self, app: AtlasApplication):
        assert app.audit().passed

    def test_validation_summary_reads_plainly(self, app: AtlasApplication):
        assert "accounting checks verified" in app.validation_summary


class TestScenarios:
    def test_a_scenario_runs_and_comes_back_as_a_scenario(self, app: AtlasApplication):
        definition = ScenarioDefinition(
            scenario_id="test",
            name="Test",
            asset_classes=(
                AssetClassParameters(
                    asset_class=CapitalCategory.SERVERS,
                    spend=Decimal(1000),
                    lead_time_years=Decimal(0),
                    useful_life_years=Decimal(6),
                    utilization_ramp=(Decimal("0.85"),),
                    revenue_yield=Decimal("0.45"),
                    operating_margin=Decimal("0.55"),
                ),
            ),
            tax_rate=Decimal("0.21"),
            discount_rate=Decimal("0.09"),
            horizon_years=8,
        )
        result = app.run_scenario(
            definition,
            requirements=(
                (
                    Lever.UTILIZATION,
                    Target.PAYBACK_YEARS,
                    Decimal(3),
                    Decimal("0.05"),
                    Decimal(1),
                ),
            ),
            sensitivities={Lever.REVENUE_YIELD: (Decimal("0.2"), Decimal("0.7"))},
        )
        assert result.status is EvidenceStatus.SCENARIO
        assert result.requirements
        assert result.sensitivities
        assert all(value.status is EvidenceStatus.SCENARIO for value in result.values)

    def test_a_scenario_serializes_into_a_bundle(self, app: AtlasApplication, tmp_path: Path):
        # Simulator output must be freezable like anything else, or it cannot be
        # cited in an article.
        definition = ScenarioDefinition(
            scenario_id="frozen",
            name="Frozen",
            asset_classes=(
                AssetClassParameters(
                    asset_class=CapitalCategory.SERVERS,
                    spend=Decimal(1000),
                    lead_time_years=Decimal(0),
                    useful_life_years=Decimal(6),
                    utilization_ramp=(Decimal("0.85"),),
                    revenue_yield=Decimal("0.45"),
                    operating_margin=Decimal("0.55"),
                ),
            ),
            tax_rate=Decimal("0.21"),
            discount_rate=Decimal("0.09"),
            horizon_years=8,
        )
        result = app.run_scenario(definition)
        with_scenario = app.bundle.model_copy(update={"scenarios": (result,)})
        path = write_bundle(with_scenario, tmp_path)
        reloaded = AtlasApplication.from_path(path)
        assert len(reloaded.bundle.scenarios) == 1
        assert reloaded.bundle.scenarios[0].definition.scenario_id == "frozen"


def test_loading_from_a_stored_bundle_is_offline(app: AtlasApplication, tmp_path: Path):
    path = write_bundle(app.bundle, tmp_path)
    reopened = AtlasApplication.from_path(path)
    assert reopened.bundle.entity_id == "GOOGL"
    assert len(reopened.overview()) == len(app.overview())
