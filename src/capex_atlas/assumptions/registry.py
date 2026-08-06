"""Loading and lookup for the assumption registry."""

from __future__ import annotations

import tomllib
from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Any, Self

from capex_atlas.assumptions.models import Assumption

_DATA_PACKAGE = "capex_atlas.assumptions.data"


class UnknownAssumptionError(KeyError):
    """Raised when a model asks for a parameter that is not in the registry.

    This is the failure mode the registry exists to create: reaching for an
    uncited constant should stop the calculation, not silently succeed.
    """


class AssumptionRegistry:
    def __init__(self, assumptions: dict[str, Assumption]) -> None:
        self._assumptions = assumptions

    @classmethod
    def load(cls, extra_paths: tuple[Path, ...] = ()) -> Self:
        """Load the packaged registry, plus any additional TOML files."""
        assumptions: dict[str, Assumption] = {}
        for path in _packaged_files():
            _ingest(assumptions, tomllib.loads(path.read_text(encoding="utf-8")), str(path))
        for path in extra_paths:
            _ingest(assumptions, tomllib.loads(path.read_text(encoding="utf-8")), str(path))
        return cls(assumptions)

    def get(self, assumption_id: str) -> Assumption:
        try:
            return self._assumptions[assumption_id]
        except KeyError:
            raise UnknownAssumptionError(
                f"{assumption_id!r} is not in the assumption registry. Add it with a citation "
                "rather than hardcoding the value."
            ) from None

    def for_entity(self, entity_id: str) -> list[Assumption]:
        """Universal assumptions plus those specific to *entity_id*."""
        return [
            assumption
            for assumption in self._assumptions.values()
            if assumption.entity_id in (None, entity_id)
        ]

    def entity_ids(self) -> set[str]:
        return {a.entity_id for a in self._assumptions.values() if a.entity_id is not None}

    def __iter__(self) -> Iterator[Assumption]:
        return iter(self._assumptions.values())

    def __len__(self) -> int:
        return len(self._assumptions)

    def __contains__(self, assumption_id: object) -> bool:
        return assumption_id in self._assumptions


def _packaged_files() -> Iterator[Path]:
    data_root = resources.files(_DATA_PACKAGE)
    for entry in sorted(data_root.iterdir(), key=lambda item: item.name):
        if entry.name.endswith(".toml"):
            with resources.as_file(entry) as path:
                yield path


def _ingest(target: dict[str, Assumption], document: dict[str, Any], origin: str) -> None:
    for assumption_id, body in document.items():
        if not isinstance(body, dict):
            raise ValueError(f"{origin}: entry {assumption_id!r} must be a table")
        if assumption_id in target:
            raise ValueError(f"{origin}: duplicate assumption id {assumption_id!r}")
        target[assumption_id] = Assumption(assumption_id=assumption_id, **body)
