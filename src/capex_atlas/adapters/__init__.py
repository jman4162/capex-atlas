"""Per-company normalization of disclosures that are economically alike but reported
differently."""

from capex_atlas.adapters.alphabet import ADAPTERS, AlphabetAdapter
from capex_atlas.adapters.base import (
    Availability,
    CapitalCategory,
    CompanyAdapter,
    SegmentSupport,
)

__all__ = [
    "ADAPTERS",
    "AlphabetAdapter",
    "Availability",
    "CapitalCategory",
    "CompanyAdapter",
    "SegmentSupport",
]
