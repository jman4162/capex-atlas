"""Cash-flow, capital-intensity and return metrics.

Every metric is declared with :func:`capex_atlas.provenance.metric`, so each
result carries a calculation node, an evidence status derived from its inputs,
and the formula shown to the reader.

Where practice disagrees, the disagreement is exposed as separately named
metrics rather than resolved behind a default. There is no ``roic()``; there is
``returns.roic``, ``returns.roic_average_capital`` and
``returns.roic_rd_capitalized``, and choosing between them is the analyst's job.
"""

from capex_atlas.metrics.capital import (
    capex_intensity,
    capex_to_depreciation,
    depreciation_coverage,
    net_investment,
)
from capex_atlas.metrics.cashflow import lease_adjusted_fcf, reported_fcf, standardized_fcf
from capex_atlas.metrics.returns import (
    incremental_roic,
    invested_capital_ex_cash,
    invested_capital_operating,
    nopat,
    roic,
    roic_on_average_capital,
    roic_rd_capitalized,
)

__all__ = [
    "capex_intensity",
    "capex_to_depreciation",
    "depreciation_coverage",
    "incremental_roic",
    "invested_capital_ex_cash",
    "invested_capital_operating",
    "lease_adjusted_fcf",
    "net_investment",
    "nopat",
    "reported_fcf",
    "roic",
    "roic_on_average_capital",
    "roic_rd_capitalized",
    "standardized_fcf",
]
