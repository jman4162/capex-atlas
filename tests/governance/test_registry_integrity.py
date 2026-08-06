"""Registry-wide invariants.

Per-assumption validation lives in the model; these check properties that only
hold across the registry as a whole -- above all that no company gets analytical
treatment the others do not.
"""

from __future__ import annotations

from capex_atlas.assumptions.models import AssumptionBasis
from capex_atlas.assumptions.registry import AssumptionRegistry


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
