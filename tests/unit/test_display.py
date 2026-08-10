"""How figures are written down for a reader.

Two forms, deliberately kept apart. :func:`format_value` is exact and is what a
reader checks a number against; :func:`format_compact` is what they scan. Both
round at the edge and neither is ever fed back into a calculation.

These tests exist because the lab shipped reading ``73,266,000,000.00 USD`` and
``0.206971``, neither of which anyone can take in, and because the percent branch
of the exact formatter was unreachable for the whole of v0.1 and v0.2.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from capex_atlas.schemas.decimals import (
    compact_magnitude,
    display_places,
    format_compact,
    format_value,
)


class TestTheExactForm:
    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [
            ("73266000000", "USD", "73,266,000,000.00 USD"),
            ("-162210000", "USD", "-162,210,000.00 USD"),
            ("0.20697128737234", "percent", "20.70%"),
            ("4.32659916729", "multiple", "4.326599 multiple"),
            ("3.970272", "years", "3.970272 years"),
            ("0.227008", "ratio", "0.227008"),
        ],
    )
    def test_it_spells_the_figure_out(self, value: str, unit: str, expected: str):
        assert format_value(Decimal(value), unit) == expected

    def test_percentages_keep_fixed_places(self):
        # 20.7% beside 27.88% invites the eye to compare different precisions,
        # so trailing zeros stay rather than being normalized away.
        assert format_value(Decimal("0.207"), "percent") == "20.70%"
        assert format_value(Decimal("0.2788"), "percent") == "27.88%"

    def test_percent_rounds_to_two_places_not_six(self):
        # The percent branch shared the ratio's six places until the metrics
        # started using it, which would have printed 20.697129%.
        assert display_places("percent") == 2
        assert format_value(Decimal("0.20697128737234"), "percent") == "20.70%"


class TestTheScanningForm:
    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [
            ("91447000000", "USD", "$91.4B"),
            ("73266000000", "USD", "$73.3B"),
            ("-162210000", "USD", "-$162.2M"),
            ("1500000000000", "USD", "$1.5T"),
            ("734", "USD", "$734"),
            ("0", "USD", "$0"),
            ("0.20697128737234", "percent", "20.7%"),
            ("4.32659916729", "multiple", "4.3×"),
            ("3.970272", "years", "4.0 years"),
        ],
    )
    def test_it_rounds_to_something_a_reader_can_hold(self, value: str, unit: str, expected: str):
        assert format_compact(Decimal(value), unit) == expected

    def test_a_non_dollar_currency_keeps_its_unit(self):
        # No symbol is assumed for a unit the package has not met.
        assert format_compact(Decimal("1234.5"), "EUR") == "1.2k EUR"

    def test_an_unknown_value_is_a_dash_in_both_forms(self):
        assert format_compact(None, "USD") == "—"
        assert format_value(None, "USD") == "—"


class TestTheSharedMagnitude:
    def test_axis_labels_and_cards_round_alike(self):
        # The SVG axis labeller delegates here, so a tick and the card above it
        # cannot disagree about what 73,266,000,000 rounds to.
        assert compact_magnitude(Decimal("73266000000")) == "73.3B"

    def test_small_ratios_keep_three_places(self):
        assert compact_magnitude(Decimal("0.227008")) == "0.227"
