"""Capital-vintage modelling.

A vintage is capital spent at one moment, followed through the years in which it
enters service, earns and depreciates. Modelling it apart from the aggregate
accounts is what keeps the three timings distinct: cash out now, capacity later,
depreciation later still.

The forward direction answers "what would this earn under these assumptions".
The inverse direction, in :mod:`~capex_atlas.capital_vintages.solver`, answers
"what would have to be true for this claim to hold", which is the question
public data can actually support.
"""

from capex_atlas.capital_vintages.engine import build_schedule, summarize
from capex_atlas.capital_vintages.model import (
    AssetClassParameters,
    VintageSchedule,
    VintageYear,
)
from capex_atlas.capital_vintages.solver import (
    Lever,
    RequirementResult,
    SensitivityBand,
    Target,
    required_for,
    tornado,
)

__all__ = [
    "AssetClassParameters",
    "Lever",
    "RequirementResult",
    "SensitivityBand",
    "Target",
    "VintageSchedule",
    "VintageYear",
    "build_schedule",
    "required_for",
    "summarize",
    "tornado",
]
