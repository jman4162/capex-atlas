"""Free cash flow, offered as named alternatives.

There is no single correct free-cash-flow figure, and a package that published
one would be hiding a choice rather than making it. Filers themselves disagree:
some deduct finance-lease principal, some net proceeds from asset sales, some
report a company-defined measure with its own reconciliation.

Each definition below is named for what it does. Comparing companies means
picking one and applying it to all of them, which is a decision the caller makes
in the open.
"""

from __future__ import annotations

from decimal import Decimal

from capex_atlas.provenance.metric import INHERIT, metric


@metric(
    metric_id="fcf.reported",
    version="1.0.0",
    formula="cash from operations - purchases of property and equipment",
    unit=INHERIT,
    label="free cash flow (reported basis)",
    homogeneous_inputs=True,
)
def reported_fcf(cash_from_operations: Decimal, capital_expenditure: Decimal) -> Decimal:
    """The common definition, and the one most headlines use.

    Ignores finance leases, so it understates capital intensity at filers that
    lease a meaningful share of their infrastructure.
    """
    return cash_from_operations - capital_expenditure


@metric(
    metric_id="fcf.lease_adjusted",
    version="1.0.0",
    formula=(
        "cash from operations - purchases of property and equipment "
        "- finance lease principal payments"
    ),
    unit=INHERIT,
    label="free cash flow (lease-adjusted)",
    homogeneous_inputs=True,
)
def lease_adjusted_fcf(
    cash_from_operations: Decimal,
    capital_expenditure: Decimal,
    finance_lease_principal: Decimal,
) -> Decimal:
    """Treats finance-lease principal as what it is: paying for capital assets.

    Comparing a filer that buys its data centres against one that leases them is
    misleading on the reported basis alone.
    """
    return cash_from_operations - capital_expenditure - finance_lease_principal


@metric(
    metric_id="fcf.standardized",
    version="1.0.0",
    formula=(
        "cash from operations - purchases of property and equipment "
        "+ proceeds from sales of property and equipment "
        "- finance lease principal payments"
    ),
    unit=INHERIT,
    label="free cash flow (standardized)",
    homogeneous_inputs=True,
)
def standardized_fcf(
    cash_from_operations: Decimal,
    capital_expenditure: Decimal,
    proceeds_from_disposals: Decimal,
    finance_lease_principal: Decimal,
) -> Decimal:
    """Net capital spending, including leases and asset sales.

    The most complete of the three, and the least comparable to what companies
    print in their own releases.
    """
    return (
        cash_from_operations
        - capital_expenditure
        + proceeds_from_disposals
        - finance_lease_principal
    )
