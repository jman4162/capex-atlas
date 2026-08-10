from __future__ import annotations

from decimal import Decimal

import pytest

from capex_atlas.assumptions.models import Assumption, AssumptionBasis
from capex_atlas.assumptions.registry import AssumptionRegistry
from capex_atlas.metrics import (
    capex_intensity,
    capex_to_depreciation,
    incremental_roic,
    invested_capital_ex_cash,
    invested_capital_operating,
    lease_adjusted_fcf,
    net_investment,
    nopat,
    reported_fcf,
    roic,
    roic_on_average_capital,
    roic_rd_capitalized,
    standardized_fcf,
)
from capex_atlas.provenance.graph import calculation_graph
from capex_atlas.provenance.metric import registered_metrics
from capex_atlas.schemas.decimals import format_value, quantize_for_display
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.period import FiscalPeriod
from tests.conftest import make_value

Q2 = FiscalPeriod(fiscal_year=2026, fiscal_quarter=2)


def usd(amount: str, *, status: EvidenceStatus = EvidenceStatus.REPORTED, key: str = "v"):  # type: ignore[no-untyped-def]
    return make_value(amount, status=status, unit="USD", period=Q2, value_id=key)


class TestFreeCashFlowVariants:
    def test_reported_basis(self):
        assert reported_fcf(usd("100", key="a"), usd("40", key="b")).value == Decimal("60")

    def test_lease_adjustment_lowers_it(self):
        plain = reported_fcf(usd("100", key="a"), usd("40", key="b"))
        adjusted = lease_adjusted_fcf(usd("100", key="a"), usd("40", key="b"), usd("5", key="c"))
        assert adjusted.value == Decimal("55")
        assert adjusted.value < plain.value

    def test_standardized_adds_back_disposals(self):
        result = standardized_fcf(
            usd("100", key="a"), usd("40", key="b"), usd("3", key="c"), usd("5", key="d")
        )
        assert result.value == Decimal("58")

    def test_the_three_definitions_are_distinct_metrics(self):
        # No single blessed FCF; each is separately named and separately traced.
        ids = {
            m.definition.metric_id
            for m in registered_metrics().values()
            if m.definition.metric_id.startswith("fcf.")
        }
        assert ids == {"fcf.reported", "fcf.lease_adjusted", "fcf.standardized"}

    def test_mixing_currencies_is_refused(self):
        from capex_atlas.provenance.errors import UnitMismatchError

        with pytest.raises(UnitMismatchError):
            reported_fcf(usd("100", key="a"), make_value("40", unit="EUR", period=Q2, value_id="b"))


class TestCapitalIntensity:
    def test_capex_over_revenue(self):
        result = capex_intensity(usd("25", key="a"), usd("100", key="b"))
        assert result.value == Decimal("0.25")
        # Stored as a fraction, declared as a percentage. The unit governs
        # display only, so the arithmetic above is unaffected by it.
        assert result.unit == "percent"
        assert result.formatted == "25.00%"

    def test_capex_to_depreciation_above_one_means_growth(self):
        assert capex_to_depreciation(usd("30", key="a"), usd("10", key="b")).value == Decimal("3")

    def test_net_investment_is_the_difference(self):
        assert net_investment(usd("30", key="a"), usd("10", key="b")).value == Decimal("20")

    def test_zero_revenue_is_unresolved_not_infinite(self):
        result = capex_intensity(usd("25", key="a"), usd("0", key="b"))
        assert result.value is None
        assert result.status is EvidenceStatus.UNRESOLVED


class TestReturns:
    def test_nopat_applies_the_tax_rate(self):
        rate = Assumption(
            assumption_id="test.rate",
            description="test",
            unit="ratio",
            basis=AssumptionBasis.USER_INPUT,
            value=Decimal("0.21"),
        )
        assert nopat(usd("100", key="a"), rate).value == Decimal("79.00")

    def test_statutory_rate_makes_the_result_estimated(self):
        # Nobody outside the company knows its marginal cash rate, so a return
        # computed from the statutory rate is an estimate and says so.
        rate = AssumptionRegistry.load().get("tax.us_federal_statutory_rate")
        assert nopat(usd("100", key="a"), rate).status is EvidenceStatus.ESTIMATED

    def test_invested_capital_operating(self):
        result = invested_capital_operating(usd("300", key="a"), usd("100", key="b"))
        assert result.value == Decimal("200")

    def test_excluding_cash_lowers_the_capital_base(self):
        with_cash = invested_capital_operating(usd("300", key="a"), usd("100", key="b"))
        without = invested_capital_ex_cash(
            usd("300", key="a"), usd("100", key="b"), usd("50", key="c"), usd("30", key="d")
        )
        assert without.value == Decimal("120")
        assert without.value < with_cash.value

    def test_roic_is_a_percentage(self):
        result = roic(usd("40", key="a"), usd("200", key="b"))
        assert result.value == Decimal("0.2")
        assert result.unit == "percent"
        assert result.formatted == "20.00%"

    def test_averaging_capital_raises_roic_when_the_base_grew(self):
        point = roic(usd("40", key="a"), usd("200", key="b"))
        averaged = roic_on_average_capital(
            usd("40", key="a"), usd("100", key="c"), usd("200", key="b")
        )
        assert averaged.value > point.value

    def test_zero_capital_is_unresolved(self):
        result = roic(usd("40", key="a"), usd("0", key="b"))
        assert result.status is EvidenceStatus.UNRESOLVED

    def test_capitalizing_rd_needs_an_undisclosed_life_so_it_is_a_scenario(self):
        # The R&D life is a caller's choice; the result must not read as measured.
        life_based = Assumption(
            assumption_id="test.rd_life",
            description="assumed research life",
            unit="years",
            basis=AssumptionBasis.USER_INPUT,
            value=Decimal("0.21"),
        )
        result = roic_rd_capitalized(
            usd("100", key="a"),
            usd("50", key="b"),
            usd("30", key="c"),
            usd("200", key="d"),
            usd("120", key="e"),
            life_based,
        )
        assert result.status is EvidenceStatus.SCENARIO

    def test_incremental_roic_measures_the_margin_not_the_average(self):
        result = incremental_roic(
            usd("60", key="a"), usd("40", key="b"), usd("300", key="c"), usd("200", key="d")
        )
        assert result.value == Decimal("0.2")

    def test_incremental_roic_with_no_added_capital_is_unresolved(self):
        result = incremental_roic(
            usd("60", key="a"), usd("40", key="b"), usd("200", key="c"), usd("200", key="d")
        )
        assert result.status is EvidenceStatus.UNRESOLVED


class TestPrecisionPolicy:
    def test_division_keeps_far_more_digits_than_display_shows(self):
        result = roic(usd("1", key="a"), usd("3", key="b"))
        assert len(str(result.value).split(".")[1]) > 20

    def test_display_rounds_once_at_the_edge(self):
        result = roic(usd("1", key="a"), usd("3", key="b"))
        assert result.formatted == "33.33%"

    def test_rounding_is_half_even(self):
        # Half-up would give 0.13 and 0.15; half-even avoids biasing sums upward.
        assert quantize_for_display(Decimal("0.125"), "USD") == Decimal("0.12")
        assert quantize_for_display(Decimal("0.135"), "USD") == Decimal("0.14")

    def test_percent_units_render_as_percentages(self):
        assert format_value(Decimal("0.1234"), "percent") == "12.34%"

    def test_unknown_values_render_as_a_dash(self):
        assert format_value(None, "USD") == "—"

    def test_chained_metrics_do_not_accumulate_rounding(self):
        # Each step keeps full precision; only the final display rounds.
        third = roic(usd("1", key="a"), usd("3", key="b"))
        assert third.value is not None
        restored = third.value * Decimal(3)
        assert abs(restored - Decimal(1)) < Decimal("1e-30")


def test_every_metric_declares_a_formula_and_version():
    for name, declared in registered_metrics().items():
        if name.startswith("test."):
            continue
        assert declared.definition.formula, f"{name} has no formula"
        assert declared.definition.version, f"{name} has no version"


def test_metric_results_are_traced():
    with calculation_graph() as graph:
        free_cash = reported_fcf(usd("100", key="a"), usd("40", key="b"))
        capex_intensity(usd("40", key="b"), usd("100", key="a"))
    assert len(graph) == 2
    node = graph.get(free_cash.value_id)
    assert node is not None
    assert node.formula.startswith("cash from operations")
