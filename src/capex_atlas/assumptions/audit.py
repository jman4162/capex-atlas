"""Static check for uncited constants in the calculation layer.

The assumption registry only works if nothing bypasses it. This walks the AST of
the modelling modules and reports numeric literals that should have been
registry entries.

Structural constants are exempt -- there are four quarters in a year whatever the
filing says. Anything else is a modelling choice and needs a citation, even when
it looks harmless: a hardcoded ``0.85`` utilization figure is exactly the kind of
number a reader has no way to challenge.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ALLOWED_NUMBERS: frozenset[float] = frozenset({0, 1, 2, -1, 4, 12, 100})
"""Structural constants: identity elements, halving, quarters, months, percent."""


@dataclass(frozen=True)
class LiteralViolation:
    path: Path
    line: int
    literal: str

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.line}: uncited constant {self.literal}. "
            "Move it to the assumption registry with a citation."
        )


def scan_source(source: str, path: Path = Path("<memory>")) -> list[LiteralViolation]:
    """Report uncited numeric literals in *source*."""
    tree = ast.parse(source)
    return list(_walk(tree, path))


def scan_paths(roots: tuple[Path, ...]) -> list[LiteralViolation]:
    """Report uncited numeric literals across every ``.py`` file under *roots*."""
    violations: list[LiteralViolation] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            violations.extend(scan_source(path.read_text(encoding="utf-8"), path))
    return violations


def _walk(tree: ast.AST, path: Path) -> Iterator[LiteralViolation]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_decimal_call(node.func):
            yield from _check_decimal_call(node, path)
        elif isinstance(node, ast.Constant):
            yield from _check_constant(node, path)


def _check_constant(node: ast.Constant, path: Path) -> Iterator[LiteralViolation]:
    value = node.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        return
    if float(value) in ALLOWED_NUMBERS:
        return
    yield LiteralViolation(path=path, line=node.lineno, literal=repr(value))


def _check_decimal_call(node: ast.Call, path: Path) -> Iterator[LiteralViolation]:
    for arg in node.args:
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            continue
        try:
            numeric = float(arg.value)
        except ValueError:
            continue
        if numeric in ALLOWED_NUMBERS:
            continue
        yield LiteralViolation(path=path, line=node.lineno, literal=f'Decimal("{arg.value}")')


def _is_decimal_call(func: ast.expr) -> bool:
    if isinstance(func, ast.Name):
        return func.id == "Decimal"
    if isinstance(func, ast.Attribute):
        return func.attr == "Decimal"
    return False
