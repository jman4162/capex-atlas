"""Capital intensity and the depreciation relationship.

Capex against depreciation is the closest thing the statements offer to a read on
whether a company is growing its asset base or replacing it, which is why it
appears here even though the maintenance-versus-growth split it hints at is not
observable and this package will not publish one.
"""

from __future__ import annotations

from decimal import Decimal

from capex_atlas.provenance.metric import INHERIT, metric


@metric(
    metric_id="capex.intensity",
    version="1.0.0",
    formula="purchases of property and equipment / revenue",
    unit="percent",
    label="capex intensity",
)
def capex_intensity(capital_expenditure: Decimal, revenue: Decimal) -> Decimal:
    """Capex as a share of revenue for the same period.

    Same-period by construction, which is exactly what makes it a poor return
    measure during a build-out: the spending and the revenue it will eventually
    support are years apart. Read it as a measure of intensity; productivity
    needs the vintage model.
    """
    return capital_expenditure / revenue


@metric(
    metric_id="capex.to_depreciation",
    version="1.0.0",
    formula="purchases of property and equipment / depreciation",
    unit="multiple",
    label="capex to depreciation",
)
def capex_to_depreciation(capital_expenditure: Decimal, depreciation: Decimal) -> Decimal:
    """Above one means the asset base is growing in nominal terms.

    Weakens whenever asset prices, useful lives or technology generations are
    changing, all three of which are in motion during an infrastructure cycle.
    """
    return capital_expenditure / depreciation


@metric(
    metric_id="capital.net_investment",
    version="1.0.0",
    formula="purchases of property and equipment - depreciation",
    unit=INHERIT,
    label="net investment in fixed assets",
    homogeneous_inputs=True,
)
def net_investment(capital_expenditure: Decimal, depreciation: Decimal) -> Decimal:
    """Spending above the accounting run-off of the existing base."""
    return capital_expenditure - depreciation


@metric(
    metric_id="capital.depreciation_lag",
    version="1.0.0",
    formula="depreciation / purchases of property and equipment",
    unit="percent",
    label="depreciation coverage of capex",
)
def depreciation_coverage(depreciation: Decimal, capital_expenditure: Decimal) -> Decimal:
    """How much of current spending the income statement is already recognizing.

    A falling ratio during a build-out is the depreciation lag made visible:
    cash leaves now, the expense arrives once assets are placed in service.
    """
    return depreciation / capital_expenditure
