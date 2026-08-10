"""Calculation provenance as a first-class object.

A result is not a number; it is a node in a graph whose leaves are reported facts
and registry assumptions. The graph is what lets a reader click any figure and
see the formula, the inputs and the filings underneath it.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.hashing import stable_id


class CalculationNode(BaseModel):
    """One application of one metric to one set of inputs."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    metric_id: str
    metric_version: str
    formula: str
    """Human-readable formula, kept next to the code that implements it."""

    inputs: tuple[str, ...]
    """``value_id`` of each input, in call order."""

    literal_inputs: tuple[str, ...] = ()
    """Canonical form of each argument that was neither a value nor an assumption.

    A discount rate passed as a bare ``Decimal``, or a ``None`` standing in for a
    concept the filer never tagged, is not a graph input but does change both the
    result and the node id. Recording it is what makes the id checkable: without
    it a reader cannot re-derive ``node_id`` from the node, and an audit cannot
    tell a genuine derivation from a forged one.
    """

    assumption_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    result: Decimal | None
    unit: str
    status: EvidenceStatus
    period_label: str | None = None

    @staticmethod
    def derive_id(
        metric_id: str,
        metric_version: str,
        inputs: tuple[str, ...],
        assumption_ids: tuple[str, ...],
        period_label: str | None,
    ) -> str:
        """Content-addressed node id.

        Input order is preserved rather than sorted: ``a - b`` and ``b - a`` are
        different calculations and must not collide.
        """
        return stable_id(
            "calc",
            metric_id,
            metric_version,
            list(inputs),
            sorted(assumption_ids),
            period_label,
        )
