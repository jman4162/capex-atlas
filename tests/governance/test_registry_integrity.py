"""Registry-wide invariants.

Per-assumption validation lives in the model; these check properties that only
hold across the registry as a whole -- above all that no company gets analytical
treatment the others do not.
"""

from __future__ import annotations

from decimal import Decimal

from capex_atlas.assumptions.models import AssumptionBasis
from capex_atlas.assumptions.registry import AssumptionRegistry
from capex_atlas.schemas.evidence import EvidenceStatus


def test_every_assumption_validates() -> None:
    # Loading constructs each entry, so citation rules are enforced here.
    assert len(AssumptionRegistry.load()) > 0


def test_every_entry_has_a_description() -> None:
    for assumption in AssumptionRegistry.load():
        assert assumption.description.strip(), f"{assumption.assumption_id} has no description"


def test_every_entry_declares_a_unit() -> None:
    for assumption in AssumptionRegistry.load():
        assert assumption.unit.strip(), f"{assumption.assumption_id} has no unit"


def test_cited_entries_point_at_checkable_passages() -> None:
    for assumption in AssumptionRegistry.load():
        if assumption.basis is AssumptionBasis.FILING_DISCLOSURE:
            assert assumption.citation is not None
            assert assumption.citation.is_verifiable, (
                f"{assumption.assumption_id} cites a filing without a quote, section or page"
            )


def test_treatment_is_symmetric_across_companies() -> None:
    """No company may have a bespoke parameter its peers lack.

    Asymmetry is how an author's private knowledge of one company would leak
    into the model, so the shapes must match even though the values differ.
    """
    registry = AssumptionRegistry.load()
    entities = registry.entity_ids()
    if len(entities) < 2:
        return

    def parameter_names(entity: str) -> set[str]:
        return {
            a.assumption_id.replace(f".{entity.lower()}", "").replace(f".{entity}", "")
            for a in registry
            if a.entity_id == entity
        }

    shapes = {entity: parameter_names(entity) for entity in sorted(entities)}
    reference_entity, reference = next(iter(shapes.items()))
    for entity, names in shapes.items():
        missing = reference - names
        extra = names - reference
        assert not (missing or extra), (
            f"{entity} and {reference_entity} have different parameter sets. "
            f"Only in {reference_entity}: {sorted(missing)}. Only in {entity}: {sorted(extra)}."
        )


class TestAlphabetDisclosures:
    """The first company-specific entries, and the distinction they demonstrate."""

    def test_server_life_is_a_disclosed_figure(self) -> None:
        entry = AssumptionRegistry.load().get("useful_life.servers_and_network.googl")
        assert entry.basis is AssumptionBasis.FILING_DISCLOSURE
        assert entry.status is EvidenceStatus.REPORTED
        assert entry.citation is not None
        assert entry.citation.accession == "0001652044-26-000018"
        assert "six years" in (entry.citation.quote or "")

    def test_building_life_is_a_disclosed_range(self) -> None:
        entry = AssumptionRegistry.load().get("useful_life.buildings_range.googl")
        assert isinstance(entry.value, tuple)
        assert entry.value == (Decimal(7), Decimal(40))

    def test_picking_a_point_inside_a_disclosed_range_is_the_readers_choice(self) -> None:
        # The range is disclosed; where in it a given data centre sits is not.
        # So the point estimate is user input and everything from it is a scenario.
        registry = AssumptionRegistry.load()
        disclosed = registry.get("useful_life.buildings_range.googl")
        chosen = registry.get("useful_life.buildings_point.googl")
        assert disclosed.status is EvidenceStatus.REPORTED
        assert chosen.status is EvidenceStatus.SCENARIO
        low, high = disclosed.value  # type: ignore[misc]
        assert low <= chosen.value <= high  # type: ignore[operator]

    def test_lead_time_is_unquantified_in_the_filing_so_it_is_user_input(self) -> None:
        entry = AssumptionRegistry.load().get("lead_time.technical_infrastructure.googl")
        assert entry.basis is AssumptionBasis.USER_INPUT
        assert entry.status is EvidenceStatus.SCENARIO

    def test_depreciation_start_policy_is_cited(self) -> None:
        entry = AssumptionRegistry.load().get("depreciation_start.googl")
        assert entry.citation is not None
        assert "ready for their intended use" in (entry.citation.quote or "")

    def test_no_amazon_entries_exist(self) -> None:
        assert "AMZN" not in AssumptionRegistry.load().entity_ids()
