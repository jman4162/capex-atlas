"""Building a vintage's schedule and summarizing it.

The schedule is where the three timings that ordinary ratios collapse are kept
apart: cash leaves at the vintage year, capacity arrives after the lead time,
and depreciation begins when the asset enters service rather than when it was
paid for. That separation is the whole reason a build-out can depress free cash
flow for years while the underlying returns are unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from capex_atlas.capital_vintages.model import (
    AssetClassParameters,
    VintageSchedule,
    VintageYear,
)
from capex_atlas.numerics import internal_rate_of_return, net_present_value, payback_period
from capex_atlas.provenance.metric import metric
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.values import AnalyticalValue


def build_schedule(
    parameters: Sequence[AssetClassParameters],
    *,
    tax_rate: Decimal,
    horizon_years: int,
    status: EvidenceStatus | None = None,
) -> VintageSchedule:
    """Lay one vintage out year by year.

    Year zero is the spending year. Everything else follows from the parameters.
    """
    if not parameters:
        raise ValueError("a vintage needs at least one asset class")
    if horizon_years < 1:
        raise ValueError("horizon must cover at least one year")

    rows: list[VintageYear] = []
    for year in range(horizon_years + 1):
        rows.append(_year_row(parameters, year=year, tax_rate=tax_rate, horizon=horizon_years))

    weakest = status or EvidenceStatus.weakest(*(p.status for p in parameters))
    return VintageSchedule(
        parameters=tuple(parameters),
        years=tuple(rows),
        status=weakest,
        tax_rate=tax_rate,
    )


def _year_row(
    parameters: Sequence[AssetClassParameters],
    *,
    year: int,
    tax_rate: Decimal,
    horizon: int,
) -> VintageYear:
    outflow = Decimal(0)
    revenue = Decimal(0)
    depreciation = Decimal(0)
    maintenance = Decimal(0)
    residual = Decimal(0)
    cash_operating_profit = Decimal(0)
    utilization_weighted = Decimal(0)
    capital_in_service = Decimal(0)
    in_service = False

    for asset in parameters:
        if year == 0:
            outflow += asset.spend

        service_start = int(asset.lead_time_years)
        retirement_year = service_start + int(asset.useful_life_years)
        years_running = year - service_start

        if service_start <= year < retirement_year:
            in_service = True
            utilization = asset.utilization_in(years_running)
            asset_revenue = asset.spend * asset.revenue_yield * utilization
            revenue += asset_revenue
            cash_operating_profit += asset_revenue * asset.operating_margin
            maintenance += asset_revenue * asset.maintenance_rate
            capital_in_service += asset.spend
            utilization_weighted += utilization * asset.spend
            if asset.useful_life_years > 0:
                depreciation += asset.spend / asset.useful_life_years

        # Whatever the asset is worth is recovered when it retires, or at the
        # horizon if the model stops first.
        if asset.residual_value_rate and year == min(retirement_year, horizon):
            residual += asset.spend * asset.residual_value_rate

    # Depreciation is not a cash flow, but it does shelter cash from tax, and
    # during a build-out that shield arrives years after the money was spent.
    # Taxing cash profit directly would erase the effect this model exists to
    # show, so tax is computed on profit after depreciation and then subtracted
    # from cash profit.
    taxable_income = cash_operating_profit - depreciation
    tax = taxable_income * tax_rate if taxable_income > 0 else Decimal(0)
    free_cash_flow = -outflow + cash_operating_profit - tax - maintenance + residual

    return VintageYear(
        year=year,
        capital_outflow=outflow,
        in_service=in_service,
        utilization=(
            utilization_weighted / capital_in_service if capital_in_service else Decimal(0)
        ),
        revenue=revenue,
        depreciation=depreciation,
        operating_profit=cash_operating_profit,
        tax=tax,
        maintenance_capital=maintenance,
        residual_value=residual,
        free_cash_flow=free_cash_flow,
    )


@metric(
    metric_id="vintage.npv",
    version="1.0.0",
    formula="sum(free cash flow_t / (1 + discount rate)^t)",
    unit="USD",
    label="vintage net present value",
)
def _npv_metric(cash_flows: object, discount_rate: Decimal) -> Decimal | None:
    assert isinstance(cash_flows, tuple)
    return net_present_value(cash_flows, discount_rate)


@metric(
    metric_id="vintage.irr",
    version="1.0.0",
    formula="rate where sum(free cash flow_t / (1 + rate)^t) = 0",
    unit="ratio",
    label="vintage internal rate of return",
)
def _irr_metric(cash_flows: object) -> Decimal | None:
    assert isinstance(cash_flows, tuple)
    return internal_rate_of_return(cash_flows)


@metric(
    metric_id="vintage.payback",
    version="1.0.0",
    formula="years until cumulative free cash flow turns positive",
    unit="years",
    label="vintage payback period",
)
def _payback_metric(cash_flows: object) -> Decimal | None:
    assert isinstance(cash_flows, tuple)
    return payback_period(cash_flows)


def summarize(schedule: VintageSchedule, *, discount_rate: Decimal) -> dict[str, AnalyticalValue]:
    """Net present value, internal rate of return and payback for a vintage.

    Each comes back through the metric kernel carrying the schedule's status, so
    a return computed from an assumed utilization ramp is visibly a scenario
    rather than a measurement.
    """
    flows = schedule.cash_flows
    results = {
        "npv": _npv_metric(flows, discount_rate),
        "irr": _irr_metric(flows),
        "payback": _payback_metric(flows),
    }
    return {
        name: value.model_copy(
            update={"status": EvidenceStatus.weakest(value.status, schedule.status)}
        )
        for name, value in results.items()
    }
