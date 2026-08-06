"""Epistemic status of a number.

The central invariant of this package: reported, derived, estimated and scenario
values are never silently mixed. That is enforced here rather than by convention,
because every calculation propagates status to its *weakest* input.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self


class EvidenceStatus(StrEnum):
    """How much epistemic weight a number carries.

    The order below is the strength order. ``UNRESOLVED`` is deliberately the
    weakest: a calculation that depends on something we could not determine is
    itself undetermined, not merely an estimate.
    """

    REPORTED = "reported"
    """Stated by the company in a filing or release."""

    DERIVED = "derived"
    """Computed deterministically from reported values alone."""

    ESTIMATED = "estimated"
    """Depends on a judgement the company did not disclose."""

    SCENARIO = "scenario"
    """Depends on a user-chosen assumption; a what-if, not a measurement."""

    UNRESOLVED = "unresolved"
    """Could not be determined from available evidence."""

    @property
    def rank(self) -> int:
        """Position in the strength order; higher is weaker."""
        return _RANK[self]

    @property
    def glyph(self) -> str:
        """Single-character marker used in charts, tables and reports."""
        return _GLYPH[self]

    @classmethod
    def weakest(cls, *statuses: EvidenceStatus) -> Self:
        """Return the weakest of *statuses*.

        Called with no arguments this returns ``REPORTED``, the identity for the
        fold, which only makes sense for a value with no inputs at all.
        """
        weakest = max(statuses, key=lambda status: _RANK[status], default=cls.REPORTED)
        return cls(weakest)


_RANK: dict[EvidenceStatus, int] = {
    EvidenceStatus.REPORTED: 0,
    EvidenceStatus.DERIVED: 1,
    EvidenceStatus.ESTIMATED: 2,
    EvidenceStatus.SCENARIO: 3,
    EvidenceStatus.UNRESOLVED: 4,
}

_GLYPH: dict[EvidenceStatus, str] = {
    EvidenceStatus.REPORTED: "●",
    EvidenceStatus.DERIVED: "◆",
    EvidenceStatus.ESTIMATED: "▲",
    EvidenceStatus.SCENARIO: "○",
    EvidenceStatus.UNRESOLVED: "!",
}
