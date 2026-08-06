from __future__ import annotations

from decimal import Decimal

import pytest

from capex_atlas.capital_vintages import (
    AssetClassParameters,
    Lever,
    Target,
    build_schedule,
    required_for,
    summarize,
    tornado,
)
from capex_atlas.numerics import internal_rate_of_return, net_present_value, payback_period
from capex_atlas.schemas.capital import CapitalCategory
from capex_atlas.schemas.evidence import EvidenceStatus

TAX = Decimal("0.21")
DISCOUNT = Decimal("0.09")


def servers(**overrides: object) -> AssetClassParameters:
    fields: dict[str, object] = {
        "asset_class": CapitalCategory.SERVERS,
        "spend": Decimal(1000),
        "lead_time_years": Decimal(0),
        "useful_life_years": Decimal(6),
        "utilization_ramp": (Decimal("0.4"), Decimal("0.7"), Decimal("0.9")),
        "revenue_yield": Decimal("0.5"),
        "operating_margin": Decimal("0.5"),
    }
    fields.update(overrides)
    return AssetClassParameters(**fields)  # type: ignore[arg-type]


def shell(**overrides: object) -> AssetClassParameters:
    fields: dict[str, object] = {
        "asset_class": CapitalCategory.BUILDINGS,
        "spend": Decimal(1000),
        "lead_time_years": Decimal(2),
        "useful_life_years": Decimal(25),
        "utilization_ramp": (Decimal(1),),
        "revenue_yield": Decimal("0.15"),
        "operating_margin": Decimal("0.5"),
    }
    fields.update(overrides)
    return AssetClassParameters(**fields)  # type: ignore[arg-type]


class TestNumerics:
    def test_npv_discounts_from_period_zero(self):
        flows = [Decimal(-100), Decimal(110)]
        assert net_present_value(flows, Decimal("0.10")) == Decimal(0)

    def test_irr_recovers_a_known_rate(self):
        rate = internal_rate_of_return([Decimal(-100), Decimal(110)])
        assert rate is not None
        assert abs(rate - Decimal("0.10")) < Decimal("0.0001")

    def test_irr_is_undefined_without_a_sign_change(self):
        # A series that never turns positive has no rate of return.
        assert internal_rate_of_return([Decimal(-100), Decimal(-50)]) is None

    def test_irr_of_an_empty_series_is_undefined(self):
        assert internal_rate_of_return([]) is None

    def test_payback_interpolates_within_the_year(self):
        years = payback_period([Decimal(-100), Decimal(50), Decimal(50), Decimal(100)])
        assert years == Decimal(2)

    def test_payback_is_none_when_the_outlay_never_returns(self):
        assert payback_period([Decimal(-100), Decimal(10)]) is None


class TestScheduleTiming:
    def test_cash_leaves_in_year_zero(self):
        schedule = build_schedule([servers()], tax_rate=TAX, horizon_years=8)
        assert schedule.years[0].capital_outflow == Decimal(1000)
        assert all(y.capital_outflow == 0 for y in schedule.years[1:])

    def test_nothing_earns_during_the_lead_time(self):
        schedule = build_schedule([shell()], tax_rate=TAX, horizon_years=8)
        assert schedule.years[0].revenue == 0
        assert schedule.years[1].revenue == 0
        assert schedule.years[2].revenue > 0

    def test_depreciation_starts_at_service_not_at_purchase(self):
        # The disclosed policy, and the reason a build-out hits cash long before
        # it hits reported profit.
        schedule = build_schedule([shell()], tax_rate=TAX, horizon_years=8)
        assert schedule.years[0].depreciation == 0
        assert schedule.years[1].depreciation == 0
        assert schedule.years[2].depreciation > 0

    def test_assets_stop_earning_after_their_useful_life(self):
        schedule = build_schedule([servers()], tax_rate=TAX, horizon_years=10)
        assert schedule.years[5].revenue > 0
        assert schedule.years[6].revenue == 0

    def test_first_service_year_reflects_the_lead_time(self):
        assert build_schedule([shell()], tax_rate=TAX, horizon_years=8).first_service_year == 2

    def test_utilization_follows_the_ramp_then_holds(self):
        schedule = build_schedule([servers()], tax_rate=TAX, horizon_years=8)
        assert [schedule.years[i].utilization for i in (0, 1, 2, 3)] == [
            Decimal("0.4"),
            Decimal("0.7"),
            Decimal("0.9"),
            Decimal("0.9"),
        ]

    def test_residual_value_arrives_at_retirement(self):
        schedule = build_schedule(
            [servers(residual_value_rate=Decimal("0.05"))], tax_rate=TAX, horizon_years=10
        )
        assert schedule.years[6].residual_value == Decimal(50)

    def test_horizon_must_cover_a_year(self):
        with pytest.raises(ValueError, match="at least one year"):
            build_schedule([servers()], tax_rate=TAX, horizon_years=0)

    def test_a_vintage_needs_an_asset_class(self):
        with pytest.raises(ValueError, match="at least one asset class"):
            build_schedule([], tax_rate=TAX, horizon_years=5)


class TestTaxShield:
    def test_depreciation_reduces_tax(self):
        with_shield = build_schedule([servers()], tax_rate=TAX, horizon_years=8)
        without_shield = build_schedule(
            [servers(useful_life_years=Decimal(6))], tax_rate=Decimal(0), horizon_years=8
        )
        assert with_shield.years[2].tax > 0
        assert without_shield.years[2].tax == 0

    def test_no_tax_when_depreciation_exceeds_cash_profit(self):
        # Early in a ramp the shield covers the whole profit, which is exactly
        # when a build-out looks least profitable on the income statement.
        schedule = build_schedule([servers()], tax_rate=TAX, horizon_years=8)
        assert schedule.years[0].operating_profit > 0
        assert schedule.years[0].tax == 0


class TestSummary:
    def test_summary_reports_npv_irr_and_payback(self):
        schedule = build_schedule([servers()], tax_rate=TAX, horizon_years=8)
        summary = summarize(schedule, discount_rate=DISCOUNT)
        assert set(summary) == {"npv", "irr", "payback"}
        assert summary["payback"].value is not None

    def test_every_vintage_output_is_a_scenario(self):
        # The ramp, yield and margin are all the reader's choices, so nothing
        # downstream may present itself as measured.
        summary = summarize(
            build_schedule([servers()], tax_rate=TAX, horizon_years=8), discount_rate=DISCOUNT
        )
        assert all(value.status is EvidenceStatus.SCENARIO for value in summary.values())

    def test_a_vintage_that_never_pays_back_says_so(self):
        summary = summarize(
            build_schedule([servers(revenue_yield=Decimal("0.01"))], tax_rate=TAX, horizon_years=8),
            discount_rate=DISCOUNT,
        )
        assert summary["payback"].value is None
        assert summary["payback"].status is EvidenceStatus.UNRESOLVED

    def test_longer_lead_time_lowers_present_value(self):
        prompt = summarize(
            build_schedule([shell(lead_time_years=Decimal(1))], tax_rate=TAX, horizon_years=20),
            discount_rate=DISCOUNT,
        )
        delayed = summarize(
            build_schedule([shell(lead_time_years=Decimal(4))], tax_rate=TAX, horizon_years=20),
            discount_rate=DISCOUNT,
        )
        assert prompt["npv"].value > delayed["npv"].value


class TestWhatMustBeTrue:
    def test_solves_the_utilization_a_payback_claim_requires(self):
        result = required_for(
            [servers()],
            lever=Lever.UTILIZATION,
            target=Target.PAYBACK_YEARS,
            target_value=Decimal(3),
            tax_rate=TAX,
            discount_rate=DISCOUNT,
            horizon_years=8,
            search_low=Decimal("0.05"),
            search_high=Decimal(1),
        )
        assert result.achievable
        assert result.required is not None
        assert Decimal("0.05") < result.required <= Decimal(1)

    def test_an_impossible_claim_returns_no_number_and_says_why(self):
        # Nothing in a 0 to 100 percent utilization range pays this back in a
        # year, and reporting that is more useful than a number would be.
        result = required_for(
            [servers(revenue_yield=Decimal("0.02"))],
            lever=Lever.UTILIZATION,
            target=Target.PAYBACK_YEARS,
            target_value=Decimal(1),
            tax_rate=TAX,
            discount_rate=DISCOUNT,
            horizon_years=8,
            search_low=Decimal("0.01"),
            search_high=Decimal(1),
        )
        assert not result.achievable
        assert "cannot hold anywhere" in result.describe()

    def test_solves_the_margin_an_irr_claim_requires(self):
        result = required_for(
            [servers()],
            lever=Lever.OPERATING_MARGIN,
            target=Target.IRR,
            target_value=Decimal("0.15"),
            tax_rate=TAX,
            discount_rate=DISCOUNT,
            horizon_years=8,
            search_low=Decimal("0.05"),
            search_high=Decimal("0.95"),
        )
        assert result.achievable

    def test_requirements_are_scenarios(self):
        result = required_for(
            [servers()],
            lever=Lever.UTILIZATION,
            target=Target.NPV_BREAKEVEN,
            target_value=Decimal(0),
            tax_rate=TAX,
            discount_rate=DISCOUNT,
            horizon_years=8,
            search_low=Decimal("0.01"),
            search_high=Decimal(1),
        )
        assert result.status is EvidenceStatus.SCENARIO

    def test_the_description_names_the_lever_and_the_target(self):
        result = required_for(
            [servers()],
            lever=Lever.UTILIZATION,
            target=Target.NPV_BREAKEVEN,
            target_value=Decimal(0),
            tax_rate=TAX,
            discount_rate=DISCOUNT,
            horizon_years=8,
            search_low=Decimal("0.01"),
            search_high=Decimal(1),
        )
        assert "utilization" in result.describe()


class TestSensitivity:
    def test_tornado_ranks_levers_by_how_much_they_move_the_answer(self):
        bands = tornado(
            [servers()],
            levers={
                Lever.REVENUE_YIELD: (Decimal("0.3"), Decimal("0.7")),
                Lever.OPERATING_MARGIN: (Decimal("0.45"), Decimal("0.55")),
            },
            tax_rate=TAX,
            discount_rate=DISCOUNT,
            horizon_years=8,
        )
        swings = [band.swing for band in bands]
        assert swings == sorted(swings, reverse=True)
        assert bands[0].lever is Lever.REVENUE_YIELD

    def test_each_band_records_the_range_it_searched(self):
        [band] = tornado(
            [servers()],
            levers={Lever.OPERATING_MARGIN: (Decimal("0.4"), Decimal("0.6"))},
            tax_rate=TAX,
            discount_rate=DISCOUNT,
            horizon_years=8,
        )
        assert band.low_input == Decimal("0.4")
        assert band.high_input == Decimal("0.6")


class TestMixedAssetVintage:
    def test_shell_and_servers_enter_service_at_different_times(self):
        schedule = build_schedule([shell(), servers()], tax_rate=TAX, horizon_years=12)
        assert schedule.total_spend == Decimal(2000)
        # Servers earn immediately, the shell only after its lead time.
        assert schedule.years[0].revenue > 0
        assert schedule.years[3].revenue > schedule.years[0].revenue

    def test_the_shell_outlives_the_servers(self):
        schedule = build_schedule([shell(), servers()], tax_rate=TAX, horizon_years=12)
        assert schedule.years[10].revenue > 0
        assert schedule.years[10].depreciation > 0
