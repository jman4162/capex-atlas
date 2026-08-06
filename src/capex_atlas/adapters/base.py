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

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from capex_atlas.normalization.calendar import FiscalCalendar
from capex_atlas.schemas.facts import Statement


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

    def segment_support(self, source: str) -> SegmentSupport:
        """Whether *source* can supply segment detail for this filer."""
        ...
