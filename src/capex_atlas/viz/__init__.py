"""Chart rendering.

Two outputs from one grammar: Plotly figure dictionaries for the interactive lab,
and static SVG for anything committed. Neither path needs a browser, and neither
loses the evidence status of the values it draws.
"""

from capex_atlas.viz.render import ChartDataError, render
from capex_atlas.viz.svg import UnsupportedFigureError, render_svg

__all__ = ["ChartDataError", "UnsupportedFigureError", "render", "render_svg"]
