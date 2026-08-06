from __future__ import annotations

from decimal import Decimal

import pytest

from capex_atlas.assumptions.models import Assumption, AssumptionBasis
from capex_atlas.assumptions.registry import AssumptionRegistry, UnknownAssumptionError
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.source import SourceKind, SourceReference

FILING_CITATION = SourceReference(
    kind=SourceKind.SEC_FILING,
    accession="0000000000-26-000000",
    section="Note 1 - Property and Equipment",
    quote="Servers are depreciated over six years.",
)


def build(**overrides: object) -> Assumption:
    fields: dict[str, object] = {
        "assumption_id": "test.parameter",
        "description": "a parameter",
        "unit": "years",
        "basis": AssumptionBasis.FILING_DISCLOSURE,
        "value": Decimal("6"),
        "citation": FILING_CITATION,
    }
    fields.update(overrides)
    return Assumption(**fields)  # type: ignore[arg-type]


class TestCitationRules:
    def test_filing_disclosure_accepts_a_full_citation(self):
        assert build().status is EvidenceStatus.REPORTED

    def test_filing_disclosure_requires_a_citation(self):
        with pytest.raises(ValueError, match="requires a citation"):
            build(citation=None)

    def test_filing_citation_requires_an_accession(self):
        loose = SourceReference(kind=SourceKind.SEC_FILING, section="Note 1")
        with pytest.raises(ValueError, match="requires an accession"):
            build(citation=loose)

    def test_filing_citation_must_point_at_a_passage(self):
        # An accession number alone does not let a reader check anything.
        bare = SourceReference(kind=SourceKind.SEC_FILING, accession="1")
        with pytest.raises(ValueError, match="quote, section or page"):
            build(citation=bare)

    def test_third_party_requires_a_url(self):
        with pytest.raises(ValueError, match="requires a URL"):
            build(basis=AssumptionBasis.PUBLISHED_THIRD_PARTY, citation=FILING_CITATION)

    def test_derived_must_not_pin_a_value(self):
        with pytest.raises(ValueError, match="must not pin a value"):
            build(basis=AssumptionBasis.DERIVED_FROM_FACTS, citation=None)

    def test_user_input_needs_no_citation(self):
        free = build(basis=AssumptionBasis.USER_INPUT, citation=None)
        assert free.status is EvidenceStatus.SCENARIO


class TestBasisToStatus:
    @pytest.mark.parametrize(
        ("basis", "expected"),
        [
            (AssumptionBasis.FILING_DISCLOSURE, EvidenceStatus.REPORTED),
            (AssumptionBasis.DERIVED_FROM_FACTS, EvidenceStatus.DERIVED),
            (AssumptionBasis.PUBLISHED_THIRD_PARTY, EvidenceStatus.ESTIMATED),
            (AssumptionBasis.USER_INPUT, EvidenceStatus.SCENARIO),
        ],
    )
    def test_every_basis_maps_to_a_status(self, basis: AssumptionBasis, expected: EvidenceStatus):
        assert _status_for(basis) is expected

    def test_there_is_no_judgement_basis(self):
        # An author's private prior can only enter as user_input, which marks
        # everything downstream as a scenario.
        assert "judgement" not in {b.value for b in AssumptionBasis}
        assert "judgment" not in {b.value for b in AssumptionBasis}


def _status_for(basis: AssumptionBasis) -> EvidenceStatus:
    if basis is AssumptionBasis.DERIVED_FROM_FACTS:
        return build(basis=basis, value=None, citation=None).status
    if basis is AssumptionBasis.PUBLISHED_THIRD_PARTY:
        url_citation = SourceReference(kind=SourceKind.THIRD_PARTY, url="https://example.org")
        return build(basis=basis, citation=url_citation).status
    if basis is AssumptionBasis.USER_INPUT:
        return build(basis=basis, citation=None).status
    return build(basis=basis).status


class TestRegistry:
    def test_packaged_registry_loads(self):
        registry = AssumptionRegistry.load()
        assert len(registry) > 0

    def test_lookup_by_id(self):
        registry = AssumptionRegistry.load()
        assumption = registry.get("tax.us_federal_statutory_rate")
        assert assumption.value == Decimal("0.21")

    def test_unknown_id_explains_the_rule(self):
        registry = AssumptionRegistry.load()
        with pytest.raises(UnknownAssumptionError, match="rather than hardcoding"):
            registry.get("server.useful_life.invented")

    def test_sequence_values_load_as_decimals(self):
        registry = AssumptionRegistry.load()
        ramp = registry.get("vintage.utilization_ramp.illustrative")
        assert isinstance(ramp.value, tuple)
        assert ramp.value[0] == Decimal("0.35")

    def test_for_entity_includes_universal_assumptions(self):
        registry = AssumptionRegistry.load()
        assert registry.for_entity("GOOGL")
