"""Nothing may bypass the assumption registry.

These tests are the mechanical half of the project's conflict-of-interest
posture: a modelling constant that cannot be traced to a filing, a public source
or an explicit user choice fails the build. That is a stronger guarantee than any
disclaimer, and it applies to every contributor equally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capex_atlas.assumptions.audit import scan_paths, scan_source

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "capex_atlas"

MODELLING_PACKAGES = (
    SRC / "metrics",
    SRC / "capital_vintages",
    SRC / "scenarios",
    SRC / "accounting",
)


class TestScanner:
    def test_flags_a_bare_float(self):
        violations = scan_source("def ramp():\n    return 0.85\n")
        assert [v.literal for v in violations] == ["0.85"]

    def test_flags_a_decimal_string_literal(self):
        violations = scan_source('from decimal import Decimal\nX = Decimal("0.21")\n')
        assert [v.literal for v in violations] == ['Decimal("0.21")']

    def test_flags_an_arbitrary_integer(self):
        violations = scan_source("def life():\n    return 6\n")
        assert [v.literal for v in violations] == ["6"]

    def test_allows_structural_constants(self):
        assert scan_source("def average(a, b):\n    return (a + b) / 2\n") == []

    def test_allows_percent_and_quarters(self):
        assert scan_source("def annualize(q):\n    return q * 4 / 100\n") == []

    def test_ignores_strings_and_booleans(self):
        assert scan_source('FLAG = True\nNAME = "servers"\n') == []

    def test_reports_line_numbers(self):
        violations = scan_source("a = 1\nb = 0.33\n")
        assert [(v.line, v.literal) for v in violations] == [(2, "0.33")]

    def test_message_names_the_remedy(self):
        violation = scan_source("x = 0.85\n")[0]
        assert "assumption registry" in str(violation)


class TestModellingLayerIsClean:
    def test_no_uncited_constants_in_the_modelling_layer(self):
        modules = [path for root in MODELLING_PACKAGES for path in root.rglob("*.py")]
        if not modules:
            pytest.skip(
                "no modelling modules yet (M3+); the scanner is exercised by TestScanner "
                "and starts guarding as soon as metrics land"
            )
        violations = scan_paths(MODELLING_PACKAGES)
        assert not violations, "\n".join(str(v) for v in violations)
