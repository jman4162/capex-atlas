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
    """Every covered filer gets the same parameters, on the same terms.

    Asymmetry is how private knowledge of one company would leak into the model,
    so the shape is fixed even where the values and their bases differ. Alphabet
    discloses a single server life and Microsoft discloses a range; both carry a
    range entry and a point entry, and the *basis* records which of them the
    filing actually supports.

    Extra entries are allowed only when the filer disclosed something its peers
    did not, and the citation proves it. Meta quantified a useful-life extension;
    that is a fact about Meta's filing, not a bespoke tuning knob. An extra
    ``user_input`` entry would be exactly the leak this guards against.
    """
    registry = AssumptionRegistry.load()
    entities = registry.entity_ids()
    assert len(entities) >= 2, (
        "this check needs at least two covered filers to constrain anything; "
        "with one it would pass without asserting"
    )

    def parameter_names(entity: str) -> set[str]:
        return {
            a.assumption_id.replace(f".{entity.lower()}", "").replace(f".{entity}", "")
            for a in registry
            if a.entity_id == entity
        }

    shapes = {entity: parameter_names(entity) for entity in sorted(entities)}
    core = set.intersection(*shapes.values())
    assert len(core) >= 5, f"only {len(core)} parameters are common to every filer: {sorted(core)}"

    for entity, names in shapes.items():
        missing = core - names
        assert not missing, f"{entity} lacks core parameters {sorted(missing)}"

        for extra in sorted(names - core):
            full_id = next(
                a for a in registry if a.entity_id == entity and a.assumption_id.startswith(extra)
            )
            assert full_id.basis is AssumptionBasis.FILING_DISCLOSURE, (
                f"{entity} has a bespoke {full_id.basis.value} parameter its peers lack: "
                f"{full_id.assumption_id}. A parameter only one company gets must be one "
                "its filing discloses, with the citation to prove it."
            )


class TestDisclosedLives:
    """What three filers disclose about the same asset class, and how it differs.

    Every one of them gives a range for buildings. Only Alphabet gives a single
    figure for servers. The registry records that faithfully rather than
    flattening it, which is the point of separating a disclosed range from a
    point chosen inside it.
    """

    def test_every_filer_carries_a_disclosed_server_range(self) -> None:
        registry = AssumptionRegistry.load()
        for entity in ("googl", "msft", "meta"):
            entry = registry.get(f"useful_life.servers_and_network_range.{entity}")
            assert entry.basis is AssumptionBasis.FILING_DISCLOSURE
            assert entry.citation is not None and entry.citation.is_verifiable
            assert isinstance(entry.value, tuple)

    def test_a_disclosed_point_stays_reported_and_a_chosen_one_does_not(self) -> None:
        registry = AssumptionRegistry.load()
        # Alphabet states six years outright, so its point is reported-grade.
        assert (
            registry.get("useful_life.servers_and_network_point.googl").status
            is EvidenceStatus.REPORTED
        )
        # Microsoft discloses two to six and says nothing about where its fleet
        # sits, so any single figure is the reader's and marks results as what-ifs.
        assert (
            registry.get("useful_life.servers_and_network_point.msft").status
            is EvidenceStatus.SCENARIO
        )

    def test_microsofts_server_range_is_much_wider_than_metas(self) -> None:
        registry = AssumptionRegistry.load()
        msft_low, msft_high = registry.get("useful_life.servers_and_network_range.msft").value
        meta_low, meta_high = registry.get("useful_life.servers_and_network_range.meta").value
        assert (msft_high - msft_low) > (meta_high - meta_low)

    def test_every_point_estimate_sits_inside_its_disclosed_range(self) -> None:
        registry = AssumptionRegistry.load()
        for entity in ("googl", "msft", "meta"):
            for asset in ("servers_and_network", "buildings"):
                low, high = registry.get(f"useful_life.{asset}_range.{entity}").value
                point = registry.get(f"useful_life.{asset}_point.{entity}").value
                assert low <= point <= high, f"{asset}.{entity}: {point} outside {low}-{high}"

    def test_lead_time_is_never_disclosed_by_anyone(self) -> None:
        # No filer quantifies the gap between paying and placing in service, so
        # every lead time in the registry is the reader's assumption.
        registry = AssumptionRegistry.load()
        for entity in ("googl", "msft", "meta"):
            entry = registry.get(f"lead_time.technical_infrastructure.{entity}")
            assert entry.basis is AssumptionBasis.USER_INPUT

    def test_metas_life_extension_is_quantified_and_cited(self) -> None:
        """Rare and useful: a dollar figure for an accounting-estimate change."""
        entry = AssumptionRegistry.load().get("useful_life.servers_and_network_extension.meta")
        assert entry.basis is AssumptionBasis.FILING_DISCLOSURE
        assert entry.value == Decimal("2920000000")
        assert entry.citation is not None
        assert "5.5 years" in (entry.citation.quote or "")

    def test_no_amazon_entries_exist(self) -> None:
        assert "AMZN" not in AssumptionRegistry.load().entity_ids()
