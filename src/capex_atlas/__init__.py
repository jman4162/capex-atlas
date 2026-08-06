"""Capex Atlas: reproducible, source-linked models of hyperscaler capital deployment.

Python calculates; agents (in later releases) discover, classify and explain.
Every published number keeps its formula, its assumptions and its evidence.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("capex-atlas")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
