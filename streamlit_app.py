"""Streamlit Community Cloud entry point.

Cloud wants a main file at a fixed path and cannot pass the ``--bundle``
argument the lab accepts, so this shim defers to the app's own default: the
example bundle shipped with the package.

Locally, prefer `capex-atlas app`, which takes `--bundle`.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

APP = Path(__file__).parent / "apps" / "streamlit" / "app.py"

sys.path.insert(0, str(APP.parent))
runpy.run_path(str(APP), run_name="__main__")
