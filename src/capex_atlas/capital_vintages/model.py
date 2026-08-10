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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    spend: Decimal = Field(ge=0)
    """Capital committed to this class in the vintage year.

    Non-negative: a negative spend produced a positive net present value, which
    is a coherent piece of arithmetic about an incoherent vintage.
    """

    lead_time_years: Decimal = Field(ge=0)
    """Years between cash leaving and the asset entering service.

    The gap this package exists to make visible. Cash goes out now; revenue and
    depreciation both start later, and not at the same later.

    Whole years only, because the schedule has annual rows. Rounding 1.9 down to
    1 would move a data centre nearly a year earlier into service and flatter
    exactly the near-term cash drag this model exists to expose, so a fractional
    lead time is refused rather than quietly absorbed.
    """

    useful_life_years: Decimal = Field(gt=0)
    """Years the asset earns and depreciates over. Fractional lives are supported
    and prorated across the final partial year."""

    utilization_ramp: tuple[Decimal, ...]
    """Utilization in each year after entering service; the last value persists."""

    revenue_yield: Decimal = Field(ge=0)
    """Annual revenue per unit of capital at full utilization."""

    operating_margin: Decimal = Field(le=1)
    maintenance_rate: Decimal = Field(default=Decimal(0), ge=0)
    """Maintenance capital spending as a share of revenue."""

    residual_value_rate: Decimal = Field(default=Decimal(0), ge=0, le=1)
    """Share of original spend recovered at end of life."""

    status: EvidenceStatus = EvidenceStatus.SCENARIO
    """Weakest status among the assumptions behind these parameters."""

    @field_validator("lead_time_years")
    @classmethod
    def _lead_time_is_whole_years(cls, value: Decimal) -> Decimal:
        if value != value.to_integral_value():
            raise ValueError(
                f"lead_time_years must be a whole number of years, got {value}. "
                "The schedule has annual rows, so a part-year delay cannot be "
                "represented without inventing sub-annual timing."
            )
        return value

    @field_validator("utilization_ramp")
    @classmethod
    def _utilization_is_a_share(cls, value: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
        if not value:
            raise ValueError("utilization_ramp needs at least one year")
        if any(not (Decimal(0) <= item <= Decimal(1)) for item in value):
            raise ValueError(f"utilization must be between 0 and 1, got {value}")
        return value

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
