from __future__ import annotations

from decimal import Decimal

import pytest

from capex_atlas.schemas.charts import Annotation, ChartSpec, ChartType
from capex_atlas.viz.render import ChartDataError, render

SPEC = ChartSpec(
    chart_type=ChartType.CAPEX_COMPOSITION_TIMELINE,
    title="Capex by period",
    x_field="period",
    y_fields=("capex",),
    data_ref="facts",
    unit="USD",
)

BAR_SPEC = SPEC.model_copy(update={"chart_type": ChartType.KNOWN_VS_INFERRED})

DATA = {
    "period": ["2024FY", "2025FY"],
    "capex": [Decimal("52535000000"), Decimal("91447000000")],
}


class TestRendering:
    def test_produces_data_and_layout(self):
        figure = render(SPEC, DATA)
        assert set(figure) == {"data", "layout"}
        assert figure["data"][0]["y"] == [52535000000.0, 91447000000.0]

    def test_missing_x_column_is_refused(self):
        with pytest.raises(ChartDataError, match="no column"):
            render(SPEC, {"capex": [Decimal(1)]})

    def test_missing_y_column_is_refused(self):
        with pytest.raises(ChartDataError, match="missing columns"):
            render(SPEC, {"period": ["2025FY"]})

    def test_ragged_columns_are_refused(self):
        with pytest.raises(ChartDataError, match="points against"):
            render(SPEC, {"period": ["a", "b"], "capex": [Decimal(1)]})

    def test_none_values_survive_as_gaps(self):
        figure = render(SPEC, {"period": ["a", "b"], "capex": [Decimal(1), None]})
        assert figure["data"][0]["y"] == [1.0, None]


class TestStatusReachesTheMarks:
    """A chart that draws a scenario like a fact undoes everything below it."""

    def test_status_travels_into_the_trace(self):
        spec = BAR_SPEC.model_copy(update={"value_status_field": "status"})
        figure = render(spec, {**DATA, "status": ["reported", "scenario"]})
        assert figure["data"][0]["customdata"] == ["reported", "scenario"]

    def test_scenario_marks_are_hatched_and_faded(self):
        spec = BAR_SPEC.model_copy(update={"value_status_field": "status"})
        marker = render(spec, {**DATA, "status": ["reported", "scenario"]})["data"][0]["marker"]
        assert marker["pattern"]["shape"] == ["", "x"]
        assert marker["opacity"][0] > marker["opacity"][1]

    def test_hatching_does_not_rely_on_colour_alone(self):
        # A reader who cannot distinguish the palette still has to see which
        # bars are measured.
        spec = BAR_SPEC.model_copy(update={"value_status_field": "status"})
        shapes = render(spec, {**DATA, "status": ["reported", "estimated"]})["data"][0]["marker"][
            "pattern"
        ]["shape"]
        assert shapes[0] != shapes[1]

    def test_without_a_status_column_nothing_claims_to_be_reported(self):
        figure = render(SPEC, DATA)
        assert set(figure["data"][0]["customdata"]) == {"derived"}

    def test_a_named_status_column_that_is_absent_is_an_error(self):
        spec = SPEC.model_copy(update={"value_status_field": "status"})
        with pytest.raises(ChartDataError, match="no status column"):
            render(spec, DATA)

    def test_the_legend_names_the_statuses_present(self):
        spec = BAR_SPEC.model_copy(update={"value_status_field": "status"})
        figure = render(spec, {**DATA, "status": ["reported", "scenario"]})
        footer = figure["layout"]["annotations"][0]["text"]
        assert "reported" in footer and "scenario" in footer


class TestFooter:
    def test_every_chart_carries_the_disclaimer(self):
        footer = render(SPEC, DATA)["layout"]["annotations"][0]["text"]
        assert "Not investment, legal, tax or accounting advice" in footer

    def test_a_methodology_note_is_shown(self):
        spec = SPEC.model_copy(update={"methodology_note": "cash capex, excluding leases"})
        footer = render(spec, DATA)["layout"]["annotations"][0]["text"]
        assert "excluding leases" in footer

    def test_annotations_are_carried_through(self):
        spec = SPEC.model_copy(
            update={"annotations": (Annotation(x="2025FY", text="guidance raised"),)}
        )
        texts = [a["text"] for a in render(spec, DATA)["layout"]["annotations"]]
        assert "guidance raised" in texts


class TestAThinBundleStillReads:
    """A timeline with one point drew two specks in an empty frame.

    The example carried only the analyzed period for most of v0.2, so the
    capital-deployment chart looked broken rather than sparse.
    """

    def test_one_point_is_drawn_as_a_bar(self):
        spec = ChartSpec(
            chart_id="thin",
            title="One period",
            chart_type=ChartType.CAPEX_COMPOSITION_TIMELINE,
            x_field="period",
            y_fields=("capex",),
            unit="USD",
            data_ref="thin",
        )
        figure = render(spec, {"period": ["2025FY"], "capex": [Decimal(1)]})
        assert figure["data"][0]["type"] == "bar"

    def test_a_real_run_is_still_a_line(self):
        spec = ChartSpec(
            chart_id="thick",
            title="Three periods",
            chart_type=ChartType.CAPEX_COMPOSITION_TIMELINE,
            x_field="period",
            y_fields=("capex",),
            unit="USD",
            data_ref="thick",
        )
        data = {"period": ["2023FY", "2024FY", "2025FY"], "capex": [Decimal(i) for i in (1, 2, 3)]}
        assert render(spec, data)["data"][0]["type"] == "scatter"
