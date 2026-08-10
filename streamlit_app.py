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

ROOT = Path(__file__).parent
APP = ROOT / "apps" / "streamlit" / "app.py"
SRC = ROOT / "src"

# The checkout's library wins over any installed copy. Cloud serves the app
# directory straight from git but imports capex_atlas from site-packages, and it
# does not always reinstall when only the source changed, so a commit touching
# both would leave the page calling a library build that predates it. That is not
# a subtle failure -- the app dies on an ImportError at startup -- but it is an
# avoidable one, and it cannot happen if both come from the same directory.
if SRC.is_dir():
    sys.path.insert(0, str(SRC))
sys.path.insert(0, str(APP.parent))
runpy.run_path(str(APP), run_name="__main__")
