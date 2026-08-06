"""Per-company normalization.

Filers describe economically similar things differently: "technical
infrastructure", "servers and network equipment", "property and equipment". An
adapter maps one filer's vocabulary onto the shared ontology while preserving
what they actually wrote, which is preferable to forcing every company through a
single universal tag map that fits none of them.

Adapters hold structural knowledge only. Any *number* an adapter needs, such as a
useful life from an accounting-policy note, belongs in the assumption registry
with a citation.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from capex_atlas.normalization.calendar import FiscalCalendar
from capex_atlas.schemas.facts import FinancialFact, Statement


class CapitalCategory(StrEnum):
    """Economic asset classes, which cut across filers' own groupings."""

    LAND = "land"
    BUILDINGS = "buildings"
    POWER = "power"
    COOLING = "cooling"
    SERVERS = "servers"
    ACCELERATORS = "accelerators"
    NETWORKING = "networking"
    STORAGE = "storage"
    CAPITALIZED_SOFTWARE = "capitalized_software"
    FINANCE_LEASES = "finance_leases"
    CONSTRUCTION_IN_PROGRESS = "construction_in_progress"
    UNALLOCATED = "unallocated"
    """The honest bucket. Most reported capex never gets broken out further."""


class Availability(StrEnum):
    """Whether a source can answer a question at all."""

    AVAILABLE = "available"
    NOT_IN_SOURCE = "not_in_source"
    """The data exists in the filing but not in the source being read."""

    NOT_DISCLOSED = "not_disclosed"
    """The company does not publish it anywhere."""


class SegmentSupport(BaseModel):
    """What segment detail a given source can supply.

    SEC Company Facts drops XBRL dimensions, so segment revenue and operating
    income are absent from it even though the filing reports them. Saying so
    beats returning an empty list that reads like "this company has no segments".
    """

    model_config = ConfigDict(frozen=True)

    availability: Availability
    explanation: str
    known_segments: tuple[str, ...] = ()


def resolve_series(
    facts: Sequence[FinancialFact], concepts: Sequence[str]
) -> dict[str, FinancialFact]:
    """Stitch one economic series together across the tags a filer has used.

    Filers migrate XBRL concepts. Alphabet reported revenue under
    ``RevenueFromContractWithCustomerExcludingAssessedTax`` and then switched to
    ``Revenues``, so either tag alone gives a history that stops or starts
    mid-stream, and a chart built on it shows a cliff that never happened.

    *concepts* is in precedence order, most current first. Where a period has
    facts under more than one tag, the earliest-listed wins.
    """
    priority = {concept: rank for rank, concept in enumerate(concepts)}
    chosen: dict[str, tuple[int, FinancialFact]] = {}
    for fact in facts:
        rank = priority.get(fact.metric_id)
        if rank is None:
            continue
        label = fact.period.label
        incumbent = chosen.get(label)
        if incumbent is None or rank < incumbent[0]:
            chosen[label] = (rank, fact)
    return {label: fact for label, (_, fact) in chosen.items()}


@runtime_checkable
class CompanyAdapter(Protocol):
    """Structural knowledge about one filer."""

    entity_id: str
    cik: int

    def calendar(self) -> FiscalCalendar: ...

    def statement_map(self) -> dict[str, Statement]:
        """XBRL concepts this filer uses, mapped onto financial statements."""
        ...

    def capex_concepts(self) -> tuple[str, ...]:
        """Concepts that together make up cash capital expenditure."""
        ...

    def concept_aliases(self) -> dict[str, tuple[str, ...]]:
        """Canonical series names to the tags this filer has used, current first."""
        ...

    def segment_support(self, source: str) -> SegmentSupport:
        """Whether *source* can supply segment detail for this filer."""
        ...
