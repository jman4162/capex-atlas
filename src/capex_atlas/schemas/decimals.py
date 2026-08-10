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
COMPACT_PLACES: Final = 1
ONE_HUNDRED: Final = Decimal(100)

RATIO_UNITS: Final = frozenset({"ratio", "percent", "multiple", "years", "months"})

MAGNITUDES: Final = (
    (Decimal("1e12"), "T"),
    (Decimal("1e9"), "B"),
    (Decimal("1e6"), "M"),
    (Decimal("1e3"), "k"),
)
"""Thresholds for the compact form, largest first."""


def calculation_context() -> Context:
    """The context every metric body runs under."""
    return CALCULATION_CONTEXT.copy()


def display_places(unit: str) -> int:
    """How many decimal places *unit* is worth showing at full precision."""
    if unit == "percent":
        return PERCENT_PLACES
    return RATIO_PLACES if unit in RATIO_UNITS else MONEY_PLACES


def quantize_for_display(value: Decimal, unit: str) -> Decimal:
    """Round *value* to a sensible number of places for its unit.

    Display only. Never feed the result back into a calculation, or the rounding
    compounds.
    """
    return _fixed(value, display_places(unit))


def format_value(value: Decimal | None, unit: str) -> str:
    """Render a value for a human, without implying precision it lacks.

    The exact form: full magnitude, grouped digits, the unit spelled out. Used
    where a reader is checking a figure rather than scanning one — tooltips, the
    provenance tree, the CLI. :func:`format_compact` is the scanning form.
    """
    if value is None:
        return "—"
    if unit == "percent":
        # Fixed places, not normalized: a column reading 20.70% / 27.88% lines up,
        # where 20.7% / 27.88% invites the eye to compare different precisions.
        return f"{quantize_for_display(value * ONE_HUNDRED, unit):f}%"
    if unit == "ratio":
        return f"{quantize_for_display(value, unit).normalize():f}"
    if unit in RATIO_UNITS:
        return f"{quantize_for_display(value, unit).normalize():f} {unit}"
    return f"{quantize_for_display(value, unit):,f} {unit}"


def format_compact(value: Decimal | None, unit: str) -> str:
    """Render a value to be taken in at a glance.

    ``$73.3B`` rather than ``73,266,000,000.00 USD``. Fourteen digits of capex
    are unreadable on a card and the trailing pence are noise: a figure rounded
    to the nearest hundred million is the one a reader can actually hold. The
    exact form stays a hover away, so nothing is hidden, only deferred.
    """
    if value is None:
        return "—"
    if unit == "percent":
        return f"{_fixed(value * ONE_HUNDRED, COMPACT_PLACES):f}%"
    if unit == "ratio":
        return format_value(value, unit)
    if unit == "multiple":
        return f"{_fixed(value, COMPACT_PLACES):f}×"
    if unit in RATIO_UNITS:
        return f"{_fixed(value, COMPACT_PLACES):f} {unit}"
    prefix, suffix = ("$", "") if unit == "USD" else ("", f" {unit}")
    sign = "-" if value < 0 else ""
    return f"{sign}{prefix}{compact_magnitude(abs(value))}{suffix}"


def compact_magnitude(value: Decimal) -> str:
    """``73.3B`` for 73,266,000,000. Sign and currency are the caller's business.

    Shared with the SVG axis labeller, so a chart tick and the card above it
    round the same way.
    """
    for limit, letter in MAGNITUDES:
        if value >= limit:
            with localcontext(CALCULATION_CONTEXT):
                scaled = value / limit
            return f"{_fixed(scaled, COMPACT_PLACES):f}{letter}"
    if 0 < value < 1:
        return f"{_fixed(value, 3).normalize():f}"
    return f"{_fixed(value, 0):f}"


def _fixed(value: Decimal, places: int) -> Decimal:
    exponent = Decimal(1).scaleb(-places)
    with localcontext(CALCULATION_CONTEXT):
        return value.quantize(exponent, rounding=ROUND_HALF_EVEN)
