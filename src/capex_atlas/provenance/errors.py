"""Failures that should stop a calculation rather than produce a plausible number."""

from __future__ import annotations


class ProvenanceError(Exception):
    """Base class for calculation-integrity failures."""


class DuplicateMetricError(ProvenanceError):
    pass


class UnitMismatchError(ProvenanceError):
    """Inputs to an additive metric were not in the same unit.

    Adding millions to billions is the kind of error that produces a number
    nobody questions, so it is fatal rather than a warning.
    """


class PeriodMismatchError(ProvenanceError):
    """Inputs spanned different fiscal periods without the metric allowing it."""


class GraphConflictError(ProvenanceError):
    """Two different results claimed the same content-addressed node id."""
