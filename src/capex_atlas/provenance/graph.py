"""The calculation graph and the context that collects it."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from capex_atlas.provenance.errors import GraphConflictError
from capex_atlas.schemas.calculation import CalculationNode


class CalculationGraph:
    """Content-addressed store of every calculation performed in a run.

    Nodes deduplicate: computing the same metric over the same inputs twice
    yields one node, which is what makes bundles byte-comparable across runs.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, CalculationNode] = {}

    def add(self, node: CalculationNode) -> CalculationNode:
        existing = self._nodes.get(node.node_id)
        if existing is not None:
            if existing != node:
                raise GraphConflictError(
                    f"node {node.node_id} already holds a different result: "
                    f"{existing.result} vs {node.result}. The node id is derived from the "
                    "metric, its version and its inputs, so this means a metric is not "
                    "deterministic."
                )
            return existing
        self._nodes[node.node_id] = node
        return node

    def get(self, node_id: str) -> CalculationNode | None:
        return self._nodes.get(node_id)

    def ancestors(self, node_id: str) -> list[CalculationNode]:
        """Every node reachable from *node_id*, deepest last.

        Inputs that are facts or assumptions are not nodes and do not appear;
        follow ``inputs``/``assumption_ids`` on the returned nodes for those.
        """
        seen: dict[str, CalculationNode] = {}
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            node = self._nodes.get(current)
            if node is None or node.node_id in seen:
                continue
            seen[node.node_id] = node
            frontier.extend(node.inputs)
        seen.pop(node_id, None)
        return list(seen.values())

    def leaf_source_ids(self, node_id: str) -> set[str]:
        """Every source cited anywhere beneath *node_id*, including itself."""
        node = self._nodes.get(node_id)
        if node is None:
            return set()
        sources = set(node.source_ids)
        for ancestor in self.ancestors(node_id):
            sources.update(ancestor.source_ids)
        return sources

    @property
    def nodes(self) -> tuple[CalculationNode, ...]:
        return tuple(self._nodes.values())

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes


_ACTIVE: ContextVar[CalculationGraph | None] = ContextVar("capex_atlas_graph", default=None)


@contextmanager
def calculation_graph(graph: CalculationGraph | None = None) -> Iterator[CalculationGraph]:
    """Collect every metric evaluation inside the block into one graph."""
    active = graph if graph is not None else CalculationGraph()
    token = _ACTIVE.set(active)
    try:
        yield active
    finally:
        _ACTIVE.reset(token)


def active_graph() -> CalculationGraph | None:
    """The graph currently collecting nodes, if any.

    Metrics work outside a graph context -- they still build and attach their
    node -- but nothing records the lineage, so anything user-facing should run
    inside :func:`calculation_graph`.
    """
    return _ACTIVE.get()
