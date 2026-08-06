"""Parameters and schedules for one capital vintage.

A vintage is a cohort of capital spent at one moment. Modelling it separately
from the company's aggregate accounts is what lets the spending, the capacity it
eventually creates, and the depreciation it eventually recognizes sit at their
own points in time rather than being collapsed into a single quarter.

Nothing here is measured. Everything is a consequence of the parameters supplied,
which is why the result carries the weakest status among them and is almost
always a scenario.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from capex_atlas.schemas.capital import CapitalCategory
from capex_atlas.schemas.evidence import EvidenceStatus


class AssetClassParameters(BaseModel):
    """Economics of one asset class within a vintage.

    Splitting by class is the point: a data centre shell and the servers inside
    it have different lead times and lives, so treating them as one asset gets
    both the cash timing and the depreciation timing wrong.
    """

    model_config = ConfigDict(frozen=True)

    asset_class: CapitalCategory
    spend: Decimal
    """Capital committed to this class in the vintage year."""

    lead_time_years: Decimal
    """Years between cash leaving and the asset entering service.

    The gap this package exists to make visible. Cash goes out now; revenue and
    depreciation both start later, and not at the same later.
    """

    useful_life_years: Decimal
    utilization_ramp: tuple[Decimal, ...]
    """Utilization in each year after entering service; the last value persists."""

    revenue_yield: Decimal
    """Annual revenue per unit of capital at full utilization."""

    operating_margin: Decimal
    maintenance_rate: Decimal = Decimal(0)
    """Maintenance capital spending as a share of revenue."""

    residual_value_rate: Decimal = Decimal(0)
    """Share of original spend recovered at end of life."""

    status: EvidenceStatus = EvidenceStatus.SCENARIO
    """Weakest status among the assumptions behind these parameters."""

    def utilization_in(self, years_in_service: int) -> Decimal:
        """Utilization once the asset has been running *years_in_service* years."""
        if years_in_service < 0 or not self.utilization_ramp:
            return Decimal(0)
        index = min(years_in_service, len(self.utilization_ramp) - 1)
        return self.utilization_ramp[index]


class VintageYear(BaseModel):
    """One year in the life of a vintage."""

    model_config = ConfigDict(frozen=True)

    year: int
    capital_outflow: Decimal = Decimal(0)
    in_service: bool = False
    utilization: Decimal = Decimal(0)
    revenue: Decimal = Decimal(0)
    depreciation: Decimal = Decimal(0)
    operating_profit: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    maintenance_capital: Decimal = Decimal(0)
    residual_value: Decimal = Decimal(0)
    free_cash_flow: Decimal = Decimal(0)


class VintageSchedule(BaseModel):
    """A vintage's full cash and accounting profile over the modelled horizon."""

    model_config = ConfigDict(frozen=True)

    parameters: tuple[AssetClassParameters, ...]
    years: tuple[VintageYear, ...]
    status: EvidenceStatus
    tax_rate: Decimal = Field(description="Rate applied to operating profit")

    @property
    def cash_flows(self) -> tuple[Decimal, ...]:
        return tuple(year.free_cash_flow for year in self.years)

    @property
    def total_spend(self) -> Decimal:
        return sum((year.capital_outflow for year in self.years), Decimal(0))

    @property
    def first_service_year(self) -> int | None:
        for year in self.years:
            if year.in_service:
                return year.year
        return None
