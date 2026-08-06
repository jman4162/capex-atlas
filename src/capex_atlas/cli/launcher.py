"""Locating the reference lab and the shipped example after a wheel install.

Both live outside ``src/`` in the repository, and are force-included into the
wheel under the package so that ``pip install "capex-atlas[app]"`` gives someone
a working lab and something to look at in it. Without this the extra installs
Streamlit and leaves the user with no way to start it.

Paths resolve differently depending on where the package came from, so this
prefers the installed copy and falls back to the checkout.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent

BUNDLED_APP = PACKAGE_ROOT / "_app" / "app.py"
BUNDLED_EXAMPLES = PACKAGE_ROOT / "_examples"

CHECKOUT_APP = REPO_ROOT / "apps" / "streamlit" / "app.py"
CHECKOUT_EXAMPLES = REPO_ROOT / "examples"

DEFAULT_EXAMPLE = "googl-2025fy"


class AppNotInstalledError(RuntimeError):
    """The lab is not reachable from here."""


def app_path() -> Path:
    """Where the Streamlit entry point lives."""
    for candidate in (BUNDLED_APP, CHECKOUT_APP):
        if candidate.exists():
            return candidate
    raise AppNotInstalledError(
        "cannot find the Streamlit app. Install the extra with "
        '`pip install "capex-atlas[app]"`, or run from a checkout.'
    )


def examples_dir() -> Path | None:
    """Where the shipped example bundles live, if any came with this install."""
    for candidate in (BUNDLED_EXAMPLES, CHECKOUT_EXAMPLES):
        if candidate.is_dir():
            return candidate
    return None


def default_bundle() -> Path | None:
    """The example to open when the caller names none."""
    directory = examples_dir()
    if directory is None:
        return None
    candidate = directory / DEFAULT_EXAMPLE
    if (candidate / "analysis.atlas.json").exists():
        return candidate
    for child in sorted(directory.iterdir()):
        if (child / "analysis.atlas.json").exists():
            return child
    return None


def streamlit_available() -> bool:
    try:
        import streamlit  # noqa: F401
    except ImportError:
        return False
    return True
