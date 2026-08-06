"""The static writer, which has to be deterministic because its output is committed."""

from __future__ import annotations

import pytest

from capex_atlas.schemas.charts import ChartSpec, ChartType
from capex_atlas.viz.render import render
from capex_atlas.viz.svg import UnsupportedFigureError, render_svg

SPEC = ChartSpec(
    chart_type=ChartType.KNOWN_VS_INFERRED,
    title="Evidence mix",
    subtitle="by weight carried",
    x_field="status",
    y_fields=("count",),
    data_ref="evidence_mix",
    value_status_field="status",
    unit="figures",
)
DATA = {"status": ["reported", "estimated", "scenario"], "count": [4, 3, 2]}


def figure() -> dict:
    return render(SPEC, DATA)


class TestDeterminism:
    def test_the_same_figure_renders_identically(self):
        # CI fails on drift in the committed figures, so this has to hold.
        assert render_svg(figure()) == render_svg(figure())

    def test_output_carries_no_timestamp_or_random_id(self):
        svg = render_svg(figure())
        assert "date" not in svg.lower()
        assert "uuid" not in svg.lower()


class TestStatusSurvivesTheTrip:
    def test_a_scenario_bar_is_hatched(self):
        svg = render_svg(figure())
        assert "hatch-scenario" in svg

    def test_an_estimated_bar_is_hatched_differently(self):
        svg = render_svg(figure())
        assert "hatch-estimated" in svg
        assert svg.count("url(#hatch-") == 2

    def test_a_reported_bar_is_neither_faded_nor_hatched(self):
        svg = render_svg(figure())
        assert 'opacity="1.00"' in svg

    def test_hatching_does_not_depend_on_colour(self):
        # A reader who cannot distinguish the palette still sees which bars are
        # measured. Same rule as the interactive path.
        svg = render_svg(figure())
        assert "<pattern" in svg


class TestStructure:
    def test_the_title_and_subtitle_appear(self):
        svg = render_svg(figure())
        assert "Evidence mix" in svg
        assert "by weight carried" in svg

    def test_the_disclaimer_reaches_the_figure(self):
        assert "Not investment, legal, tax or accounting advice" in render_svg(figure())

    def test_every_category_is_labelled(self):
        svg = render_svg(figure())
        for label in DATA["status"]:
            assert f">{label}<" in svg

    def test_markup_is_escaped(self):
        spec = SPEC.model_copy(update={"title": "Capex <b>&</b> depreciation"})
        svg = render_svg(render(spec, DATA))
        assert "&lt;b&gt;&amp;&lt;/b&gt;" in svg

    def test_a_two_series_figure_gets_a_legend(self):
        spec = SPEC.model_copy(update={"y_fields": ("capex", "depreciation")})
        svg = render_svg(render(spec, {**DATA, "capex": [9, 8, 7], "depreciation": [3, 2, 1]}))
        assert ">capex<" in svg and ">depreciation<" in svg

    def test_negative_values_render_below_the_axis(self):
        svg = render_svg(render(SPEC, {**DATA, "count": [-5, 3, 2]}))
        assert "<rect" in svg


class TestRefusals:
    def test_an_empty_figure_is_refused(self):
        with pytest.raises(UnsupportedFigureError, match="no plottable series"):
            render_svg({"data": [], "layout": {}})

    def test_an_all_empty_series_is_refused(self):
        with pytest.raises(UnsupportedFigureError, match="every point is empty"):
            render_svg({"data": [{"type": "bar", "x": ["a"], "y": [None]}], "layout": {}})

    def test_an_unsupported_trace_type_is_refused_rather_than_guessed(self):
        figure = {"data": [{"type": "sankey", "x": ["a"], "y": [1]}], "layout": {}}
        with pytest.raises(UnsupportedFigureError, match="unsupported trace type"):
            render_svg(figure)
