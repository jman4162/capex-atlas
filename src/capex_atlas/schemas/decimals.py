"""Arithmetic precision and display rounding.

Two separate concerns, deliberately kept apart.

*Calculation* runs at high precision and never rounds intermediates. Rounding a
value in the middle of a chain then feeding it onward makes results depend on the
order operations happened to be written in, which breaks reproducibility for no
benefit.

*Display* rounds once, at the edge, to a number of places that suits the unit.
A ratio printed to twenty-eight decimal places is no more honest than one printed
to four; it is less readable and implies precision the inputs never had.

Rounding is half-even throughout. Half-up biases sums of many roundings upward,
which matters when the sums are financial.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Final

CALCULATION_PRECISION: Final = 34
"""Digits carried during calculation, matching IEEE 754 decimal128.

Comfortably beyond any reported figure's real precision, so division does not
lose digits that later subtractions would expose.
"""

CALCULATION_CONTEXT: Final = Context(prec=CALCULATION_PRECISION, rounding=ROUND_HALF_EVEN)

RATIO_PLACES: Final = 6
MONEY_PLACES: Final = 2
PERCENT_PLACES: Final = 2

RATIO_UNITS: Final = frozenset({"ratio", "percent", "multiple", "years", "months"})


def calculation_context() -> Context:
    """The context every metric body runs under."""
    return CALCULATION_CONTEXT.copy()


def quantize_for_display(value: Decimal, unit: str) -> Decimal:
    """Round *value* to a sensible number of places for its unit.

    Display only. Never feed the result back into a calculation, or the rounding
    compounds.
    """
    places = RATIO_PLACES if unit in RATIO_UNITS else MONEY_PLACES
    exponent = Decimal(1).scaleb(-places)
    with localcontext(CALCULATION_CONTEXT):
        return value.quantize(exponent, rounding=ROUND_HALF_EVEN)


def format_value(value: Decimal | None, unit: str) -> str:
    """Render a value for a human, without implying precision it lacks."""
    if value is None:
        return "—"
    if unit == "percent":
        scaled = quantize_for_display(value * Decimal(100), "percent")
        return f"{scaled.normalize():f}%"
    if unit == "ratio":
        return f"{quantize_for_display(value, unit).normalize():f}"
    if unit in RATIO_UNITS:
        return f"{quantize_for_display(value, unit).normalize():f} {unit}"
    return f"{quantize_for_display(value, unit):,f} {unit}"
