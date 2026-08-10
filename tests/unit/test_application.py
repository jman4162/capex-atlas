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


class TestTheProvenanceTreeReachesTheFilings:
    """The page promises 'the formula, the inputs and the filings beneath it'.

    It used to render one row and stop, because ``_walk`` descended only into
    calculation nodes while every leaf input is a fact the bundle stores
    separately.
    """

    def test_a_calculation_bottoms_out_in_reported_facts(self, app: AtlasApplication):
        nodes = app.lineage("free cash flow (reported basis)")
        assert len(nodes) > 1, "a formula with inputs must show them"
        leaves = [node for node in nodes if node.is_fact]
        assert {leaf.concept for leaf in leaves} == {
            "NetCashProvidedByUsedInOperatingActivities",
            "PaymentsToAcquirePropertyPlantAndEquipment",
        }

    def test_leaves_are_reported_and_carry_their_period(self, app: AtlasApplication):
        leaves = [n for n in app.lineage("free cash flow (reported basis)") if n.is_fact]
        assert all(leaf.status is EvidenceStatus.REPORTED for leaf in leaves)
        assert all(leaf.period_label for leaf in leaves)

    def test_leaves_sit_below_the_calculation_that_used_them(self, app: AtlasApplication):
        nodes = app.lineage("free cash flow (reported basis)")
        assert nodes[0].is_fact is False
        assert all(leaf.depth > nodes[0].depth for leaf in nodes if leaf.is_fact)

    def test_an_input_the_bundle_no_longer_carries_is_skipped(self, app: AtlasApplication):
        """A pruned fact costs one row, not the page."""
        stripped = AtlasApplication(app.bundle.model_copy(update={"facts": ()}))
        nodes = stripped.lineage("free cash flow (reported basis)")
        assert [node.metric_id for node in nodes] == ["fcf.reported"]


class TestTheHeadline:
    def test_it_leads_with_the_spending_itself(self, app: AtlasApplication):
        titles = [card.title for card in app.headline()]
        assert titles[:2] == ["Capital expenditure", "Depreciation"]

    def test_it_is_the_only_place_a_reported_figure_appears(self, app: AtlasApplication):
        # Every published value is a calculation, so without this the interface
        # never shows a ● despite being built to distinguish one.
        assert not any(c.status is EvidenceStatus.REPORTED for c in app.overview())
        assert any(c.status is EvidenceStatus.REPORTED for c in app.headline())

    def test_money_is_compact_and_ratios_are_percentages(self, app: AtlasApplication):
        shown = {card.title: card.display for card in app.headline()}
        assert shown["Capital expenditure"] == "$91.4B"
        assert shown["Capex intensity"] == "22.7%"
        assert shown["Capex to depreciation"] == "4.3×"

    def test_the_exact_figure_is_still_available(self, app: AtlasApplication):
        capex = next(c for c in app.headline() if c.title == "Capital expenditure")
        assert capex.formatted == "91,447,000,000.00 USD"


class TestCardTitles:
    def test_the_lookup_key_is_never_rewritten(self, app: AtlasApplication):
        """Titles are display only. ``bundle.value()`` matches the label exactly,
        so retitling in place would silently return nothing."""
        for card in app.overview():
            assert app.card(card.label) is not None

    def test_abbreviations_are_spelled_the_way_a_reader_writes_them(self, app: AtlasApplication):
        titles = {card.title for card in app.overview()}
        assert "ROIC (operating basis)" in titles
        assert "NOPAT" in titles
