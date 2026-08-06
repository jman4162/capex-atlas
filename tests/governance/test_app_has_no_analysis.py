"""The front end must stay replaceable.

A Streamlit page that computes something has taken a number outside the
provenance kernel, and swapping the front end would then mean reimplementing
analysis. So pages may talk to the service layer and to plain data types, and to
nothing that calculates.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "apps" / "streamlit"

FORBIDDEN_MODULES = {
    "capex_atlas.metrics",
    "capex_atlas.accounting",
    "capex_atlas.xbrl",
    "capex_atlas.normalization",
    "capex_atlas.sources",
    "capex_atlas.adapters",
    "capex_atlas.provenance",
}
"""Importing any of these means the page is doing analysis or I/O itself.

``capital_vintages`` and ``scenarios`` are absent from the list on purpose: the
simulator has to name asset classes and levers to build a request. It still runs
them through the service layer.
"""


def app_modules() -> list[Path]:
    return sorted(APP_DIR.rglob("*.py"))


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_there_are_app_modules_to_check() -> None:
    # Guard against this whole file passing because the app moved.
    assert app_modules(), f"no Python under {APP_DIR}"


@pytest.mark.parametrize("path", app_modules(), ids=lambda p: p.name)
def test_pages_do_not_import_the_calculation_layer(path: Path) -> None:
    offending = sorted(
        module
        for module in imported_modules(path)
        if any(module == bad or module.startswith(f"{bad}.") for bad in FORBIDDEN_MODULES)
    )
    assert not offending, (
        f"{path.name} imports {offending}. Pages render; the service layer computes. "
        "Add a method to capex_atlas.application instead."
    )


@pytest.mark.parametrize("path", app_modules(), ids=lambda p: p.name)
def test_pages_do_not_reach_the_network(path: Path) -> None:
    offending = sorted(
        module
        for module in imported_modules(path)
        if module.split(".")[0] in {"httpx", "requests", "urllib"}
    )
    assert not offending, f"{path.name} imports {offending}; browsing a bundle stays offline"


def test_the_app_shows_a_disclaimer_on_every_page() -> None:
    app = (APP_DIR / "app.py").read_text(encoding="utf-8")
    # Called once in main(), outside the per-page branch, so no page can omit it.
    assert "disclaimer_footer()" in app


def test_scenarios_run_only_on_an_explicit_submission() -> None:
    """A slider drag must not fire an expensive or nondeterministic run."""
    app = (APP_DIR / "app.py").read_text(encoding="utf-8")
    assert "st.form(" in app
    assert "form_submit_button" in app
    assert "if not submitted:" in app
