"""Per-company normalization of disclosures that are economically alike but reported
differently.

``ADAPTERS`` is the single registry. Anything that needs a filer's vocabulary
resolves it here rather than importing a concrete adapter, so adding a company is
a new module plus one entry.
"""

from capex_atlas.adapters.alphabet import AlphabetAdapter
from capex_atlas.adapters.base import (
    REQUIRED_SERIES,
    Availability,
    CapitalCategory,
    CompanyAdapter,
    SegmentSupport,
    concrete_concepts,
    resolve_series,
    resolve_value_series,
)

ADAPTERS: dict[str, CompanyAdapter] = {
    AlphabetAdapter.entity_id: AlphabetAdapter(),
}


class UnsupportedEntityError(KeyError):
    """No adapter covers this filer."""


def adapter_for(entity_id: str) -> CompanyAdapter:
    """Look up an adapter, or explain what is covered."""
    adapter = ADAPTERS.get(entity_id.upper())
    if adapter is None:
        raise UnsupportedEntityError(
            f"no adapter for {entity_id!r}. Covered filers: {sorted(ADAPTERS)}. "
            "Amazon and AWS are out of scope; see DISCLOSURE.md."
        )
    return adapter


__all__ = [
    "ADAPTERS",
    "REQUIRED_SERIES",
    "AlphabetAdapter",
    "Availability",
    "CapitalCategory",
    "CompanyAdapter",
    "SegmentSupport",
    "UnsupportedEntityError",
    "adapter_for",
    "concrete_concepts",
    "resolve_series",
    "resolve_value_series",
]
