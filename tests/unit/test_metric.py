"""The provenance kernel is the project's central mechanism; test it hard."""

from __future__ import annotations

from decimal import Decimal

import pytest

from capex_atlas.assumptions.models import Assumption, AssumptionBasis
from capex_atlas.provenance.errors import PeriodMismatchError, UnitMismatchError
from capex_atlas.provenance.graph import calculation_graph
from capex_atlas.provenance.metric import INHERIT, metric
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.period import FiscalPeriod
from tests.conftest import make_value


@metric(
    metric_id="test.difference",
    version="1.0.0",
    formula="a - b",
    unit=INHERIT,
    homogeneous_inputs=True,
)
def difference(a: Decimal, b: Decimal) -> Decimal:
    return a - b


@metric(metric_id="test.ratio", version="1.0.0", formula="a / b", unit="ratio")
def ratio(a: Decimal, b: Decimal) -> Decimal:
    return a / b


@metric(
    metric_id="test.lagged",
    version="1.0.0",
    formula="a - b across periods",
    unit=INHERIT,
    allow_mixed_periods=True,
)
def lagged(a: Decimal, b: Decimal) -> Decimal:
    return a - b


def test_computes_and_labels_the_result():
    result = difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
    assert result.value == Decimal("60")
    assert result.unit == "USD_millions"
    assert result.label == "test.difference"


def test_reported_inputs_yield_derived_not_reported():
    # A calculation is never itself "reported", however solid its inputs.
    result = difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
    assert result.status is EvidenceStatus.DERIVED


@pytest.mark.parametrize(
    "input_status",
    [EvidenceStatus.ESTIMATED, EvidenceStatus.SCENARIO],
)
def test_status_degrades_to_the_weakest_input(input_status: EvidenceStatus):
    result = difference(
        make_value("100", value_id="a"),
        make_value("40", status=input_status, value_id="b"),
    )
    assert result.status is input_status


def test_status_degrades_through_a_chain():
    scenario = make_value("10", status=EvidenceStatus.SCENARIO, value_id="s")
    first = difference(make_value("100", value_id="a"), scenario)
    second = difference(first, make_value("5", value_id="c"))
    assert second.status is EvidenceStatus.SCENARIO


def test_assumption_basis_sets_the_status():
    user_choice = Assumption(
        assumption_id="test.user_choice",
        description="illustrative",
        unit="USD_millions",
        basis=AssumptionBasis.USER_INPUT,
        value=Decimal("7"),
    )
    result = difference(make_value("100", value_id="a"), user_choice)
    assert result.value == Decimal("93")
    assert result.status is EvidenceStatus.SCENARIO
    assert result.assumption_ids == ("test.user_choice",)


def test_missing_input_short_circuits_to_unresolved():
    result = difference(make_value("100", value_id="a"), make_value(None, value_id="b"))
    assert result.value is None
    assert result.status is EvidenceStatus.UNRESOLVED


def test_zero_denominator_is_unresolved_not_a_crash():
    result = ratio(make_value("100", value_id="a"), make_value("0", value_id="b"))
    assert result.value is None
    assert result.status is EvidenceStatus.UNRESOLVED


def test_mismatched_units_are_fatal_for_additive_metrics():
    with pytest.raises(UnitMismatchError, match="share a unit"):
        difference(
            make_value("100", unit="USD_millions", value_id="a"),
            make_value("40", unit="USD_billions", value_id="b"),
        )


def test_ratio_of_differing_units_is_allowed():
    # Dividing revenue by capital is meaningful even though the units differ in
    # meaning; only additive metrics demand homogeneity.
    result = ratio(
        make_value("100", unit="USD_millions", value_id="a"),
        make_value("40", unit="USD_millions_capital", value_id="b"),
    )
    assert result.unit == "ratio"


def test_mixed_periods_are_rejected_by_default():
    q1 = FiscalPeriod(fiscal_year=2026, fiscal_quarter=1)
    q2 = FiscalPeriod(fiscal_year=2026, fiscal_quarter=2)
    with pytest.raises(PeriodMismatchError, match="2026Q1"):
        difference(
            make_value("100", period=q1, value_id="a"),
            make_value("40", period=q2, value_id="b"),
        )


def test_mixed_periods_allowed_when_the_metric_opts_in():
    q1 = FiscalPeriod(fiscal_year=2026, fiscal_quarter=1)
    q2 = FiscalPeriod(fiscal_year=2026, fiscal_quarter=2)
    result = lagged(
        make_value("100", period=q1, value_id="a"),
        make_value("40", period=q2, value_id="b"),
    )
    assert result.value == Decimal("60")
    assert result.period is None  # ambiguous by construction, so not claimed


def test_node_ids_are_deterministic_across_runs():
    first = difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
    second = difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
    assert first.value_id == second.value_id


def test_argument_order_changes_the_node_id():
    forward = difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
    reverse = difference(make_value("40", value_id="b"), make_value("100", value_id="a"))
    assert forward.value_id != reverse.value_id


def test_version_bump_changes_the_node_id():
    @metric(metric_id="test.difference_v2", version="2.0.0", formula="a - b", unit=INHERIT)
    def difference_v2(a: Decimal, b: Decimal) -> Decimal:
        return a - b

    original = difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
    bumped = difference_v2(make_value("100", value_id="a"), make_value("40", value_id="b"))
    assert original.value_id != bumped.value_id


def test_graph_records_nodes_and_lineage():
    with calculation_graph() as graph:
        inner = difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
        outer = difference(inner, make_value("10", value_id="c"))

    assert len(graph) == 2
    node = graph.get(outer.value_id)
    assert node is not None
    assert node.formula == "a - b"
    assert inner.value_id in node.inputs
    assert [ancestor.node_id for ancestor in graph.ancestors(outer.value_id)] == [inner.value_id]


def test_repeated_identical_calculations_collapse_to_one_node():
    with calculation_graph() as graph:
        difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
        difference(make_value("100", value_id="a"), make_value("40", value_id="b"))
    assert len(graph) == 1


def test_sources_propagate_up_the_graph(fact):
    from capex_atlas.schemas.values import AnalyticalValue

    reported = AnalyticalValue.from_fact(fact)
    with calculation_graph() as graph:
        result = difference(reported, make_value("40", value_id="b"))
    assert fact.source.source_id in graph.leaf_source_ids(result.value_id)


@metric(metric_id="test.bind_subtract", version="1", formula="a - b", unit="USD")
def _bind_subtract(a: Decimal, b: Decimal) -> Decimal:
    return a - b


@metric(metric_id="test.bind_add", version="1", formula="a + b", unit="USD")
def _bind_add(a: Decimal, b: Decimal = Decimal(0)) -> Decimal:
    return a + b


def _usd(amount: str, key: str):  # type: ignore[no-untyped-def]
    return make_value(amount, unit="USD", value_id=key)


class TestArgumentsBindToTheirDeclaredPositions:
    """Content-addressing is only sound if the id sees the real inputs.

    ``derive_id`` preserves input order on purpose, because ``a - b`` and
    ``b - a`` are different calculations. The call path defeated that by reading
    ``kwargs.values()``, which follows call-site insertion order and carries no
    parameter names.
    """

    def test_swapped_keyword_bindings_are_different_calculations(self):
        left, right = _usd("10", "l"), _usd("3", "r")
        with calculation_graph():
            forward = _bind_subtract(a=left, b=right)
        with calculation_graph():
            backward = _bind_subtract(b=left, a=right)
        assert forward.value == Decimal(7)
        assert backward.value == Decimal(-7)
        assert forward.formula_node_id != backward.formula_node_id, (
            "opposite results shared one node id, so the graph could not tell them apart"
        )

    def test_the_same_call_written_two_ways_is_one_calculation(self):
        left, right = _usd("10", "l"), _usd("3", "r")
        with calculation_graph():
            positional = _bind_subtract(left, right)
        with calculation_graph():
            keyword = _bind_subtract(a=left, b=right)
        assert positional.formula_node_id == keyword.formula_node_id

    def test_a_default_argument_binds_before_hashing(self):
        left = _usd("10", "l")
        with calculation_graph():
            implicit = _bind_add(left)
        with calculation_graph():
            explicit = _bind_add(left, Decimal(0))
        assert implicit.formula_node_id == explicit.formula_node_id
