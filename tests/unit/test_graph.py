from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from capex_atlas.provenance.errors import GraphConflictError
from capex_atlas.provenance.graph import CalculationGraph, active_graph, calculation_graph
from capex_atlas.provenance.metric import INHERIT, metric
from tests.conftest import make_value

_counter = itertools.count()


@metric(metric_id="test.nondeterministic", version="1.0.0", formula="counter", unit=INHERIT)
def nondeterministic(a: Decimal) -> Decimal:
    return a + Decimal(next(_counter))


@metric(metric_id="test.identity", version="1.0.0", formula="a", unit=INHERIT)
def identity(a: Decimal) -> Decimal:
    return a


def test_no_active_graph_outside_the_context():
    assert active_graph() is None


def test_metrics_work_without_a_graph():
    # The node is still built and attached; nothing records the lineage.
    result = identity(make_value("5", value_id="a"))
    assert result.value == Decimal("5")
    assert result.formula_node_id is not None


def test_context_restores_the_previous_graph():
    outer = CalculationGraph()
    with calculation_graph(outer):
        with calculation_graph():
            assert active_graph() is not outer
        assert active_graph() is outer
    assert active_graph() is None


def test_nondeterministic_metric_is_caught():
    # Same metric, same inputs, different result: the node id collides and the
    # graph refuses to hold two answers for one question.
    with pytest.raises(GraphConflictError, match="deterministic"), calculation_graph():
        nondeterministic(make_value("1", value_id="a"))
        nondeterministic(make_value("1", value_id="a"))


def test_ancestors_of_an_unknown_node_are_empty():
    graph = CalculationGraph()
    assert graph.ancestors("calc:missing") == []
    assert graph.leaf_source_ids("calc:missing") == set()


def test_membership_and_length():
    with calculation_graph() as graph:
        result = identity(make_value("5", value_id="a"))
    assert result.value_id in graph
    assert len(graph) == 1
    assert graph.nodes[0].node_id == result.value_id
