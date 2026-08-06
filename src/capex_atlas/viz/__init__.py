"""Chart rendering. Emits plain Plotly figure dictionaries, so the core package
needs no plotting dependency and a static site can consume the same JSON."""

from capex_atlas.viz.render import ChartDataError, render

__all__ = ["ChartDataError", "render"]
