"""Assumptions carry citations, or they are not assumptions -- they are guesses.

No model parameter may be a bare literal in a function body. Every default is a
registry entry with a declared basis, and the basis determines the evidence
status of everything computed from it. There is deliberately no
``basis = "judgement"``: an author's private prior can only enter the model as
``user_input``, which marks every downstream number as a scenario.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.source import SourceReference


class AssumptionBasis(StrEnum):
    FILING_DISCLOSURE = "filing_disclosure"
    """Stated in a filing. Requires an accession and a quotable passage."""

    DERIVED_FROM_FACTS = "derived_from_facts"
    """Computed at runtime from facts in the bundle; carries no fixed value."""

    PUBLISHED_THIRD_PARTY = "published_third_party"
    """From a citable public source that is not the company. Requires a URL."""

    USER_INPUT = "user_input"
    """Supplied by whoever runs the model. Any stored value is an illustrative
    starting point only, and produces scenario-status results."""


_STATUS_BY_BASIS: dict[AssumptionBasis, EvidenceStatus] = {
    AssumptionBasis.FILING_DISCLOSURE: EvidenceStatus.REPORTED,
    AssumptionBasis.DERIVED_FROM_FACTS: EvidenceStatus.DERIVED,
    AssumptionBasis.PUBLISHED_THIRD_PARTY: EvidenceStatus.ESTIMATED,
    AssumptionBasis.USER_INPUT: EvidenceStatus.SCENARIO,
}


class Assumption(BaseModel):
    """One model parameter and the evidence for its value."""

    model_config = ConfigDict(frozen=True)

    assumption_id: str
    description: str
    unit: str
    basis: AssumptionBasis
    value: Decimal | tuple[Decimal, ...] | None = None
    citation: SourceReference | None = None
    entity_id: str | None = None
    """``None`` means the assumption applies to every company.

    Entity-specific entries are how per-company accounting policy enters the
    model. They are also what the symmetry test inspects.
    """

    @property
    def status(self) -> EvidenceStatus:
        """Evidence status this assumption confers on anything using it."""
        return _STATUS_BY_BASIS[self.basis]

    @model_validator(mode="after")
    def _check_citation(self) -> Self:
        basis = self.basis
        if basis is AssumptionBasis.FILING_DISCLOSURE:
            if self.citation is None:
                raise ValueError(f"{self.assumption_id}: filing_disclosure requires a citation")
            if not self.citation.accession:
                raise ValueError(f"{self.assumption_id}: filing citation requires an accession")
            if not self.citation.is_verifiable:
                raise ValueError(
                    f"{self.assumption_id}: filing citation needs a quote, section or page "
                    "so a reader can check it"
                )
            if self.value is None:
                raise ValueError(f"{self.assumption_id}: filing_disclosure requires a value")
        elif basis is AssumptionBasis.PUBLISHED_THIRD_PARTY:
            if self.citation is None or not self.citation.url:
                raise ValueError(f"{self.assumption_id}: published_third_party requires a URL")
            if self.value is None:
                raise ValueError(f"{self.assumption_id}: published_third_party requires a value")
        elif basis is AssumptionBasis.DERIVED_FROM_FACTS:
            if self.value is not None:
                raise ValueError(
                    f"{self.assumption_id}: derived_from_facts must not pin a value; "
                    "it is computed from the bundle"
                )
        return self
