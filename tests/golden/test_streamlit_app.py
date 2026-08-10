"""The lab, driven headlessly against a bundle built from the pinned fixture.

Rendering is checked rather than assumed: an app that only proves it imports has
proved very little.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capex_atlas.bundle.builder import build_analysis
from capex_atlas.bundle.io import write_bundle
from capex_atlas.schemas.source import SourceKind, SourceReference

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "apps" / "streamlit" / "app.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "googl_companyfacts_trimmed.json"


@pytest.fixture(scope="module")
def bundle_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    bundle = build_analysis(
        json.loads(FIXTURE.read_text()),
        entity_id="GOOGL",
        period_label="2025FY",
        source=SourceReference(kind=SourceKind.SEC_FILING, url="https://data.sec.gov/x"),
    )
    target = tmp_path_factory.mktemp("bundle") / "googl-2025fy"
    write_bundle(bundle, target)
    return target


def launch(bundle_dir: Path, monkeypatch: pytest.MonkeyPatch, page: str | None = None) -> AppTest:
    monkeypatch.setattr(sys, "argv", ["app.py", "--bundle", str(bundle_dir)])
    test = AppTest.from_file(str(APP), default_timeout=120)
    test.run()
    if page is not None:
        test.sidebar.radio[0].set_value(page).run()
    return test


def test_the_app_starts_without_error(bundle_dir: Path, monkeypatch: pytest.MonkeyPatch):
    app = launch(bundle_dir, monkeypatch)
    assert not app.exception
    assert app.title[0].value == "GOOGL · 2025FY"


def test_the_overview_shows_every_headline_figure(
    bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    app = launch(bundle_dir, monkeypatch)
    labels = [metric.label for metric in app.metric]
    # Four headline figures, then every published value grouped beneath them.
    # Two of the eleven are already in the headline and are not repeated.
    assert len(app.metric) == 4 + 9
    assert len(labels) == len(set(labels)), f"a figure is rendered twice: {labels}"
    assert any("Free cash flow" in label for label in labels)
    assert any("Capital expenditure" in label for label in labels), (
        "the spending itself must appear, not only the ratios built from it"
    )


def test_the_overview_shows_a_reported_figure(bundle_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Every published value is a calculation, so without the headline facts the
    lab would never display a single ● despite being built to mark them."""
    app = launch(bundle_dir, monkeypatch)
    assert any("●" in metric.label for metric in app.metric)


def test_money_is_compact_and_ratios_are_percentages(
    bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    app = launch(bundle_dir, monkeypatch)
    values = [metric.value for metric in app.metric]
    assert "$91.4B" in values, "capex should read as billions, not fourteen digits"
    assert "22.7%" in values, "capex intensity is a percentage, not a bare 0.227008"
    assert not any(value.endswith(".00 USD") for value in values)


def test_status_glyphs_reach_the_interface(bundle_dir: Path, monkeypatch: pytest.MonkeyPatch):
    # A reader must be able to see which figures are measured without reading
    # the methodology page first.
    app = launch(bundle_dir, monkeypatch)
    labels = " ".join(metric.label for metric in app.metric)
    assert "◆" in labels
    assert "▲" in labels
    assert "!" in labels


def test_an_unresolved_figure_renders_as_a_dash(bundle_dir: Path, monkeypatch: pytest.MonkeyPatch):
    app = launch(bundle_dir, monkeypatch)
    unresolved = [m for m in app.metric if "standardized" in m.label]
    assert unresolved
    assert unresolved[0].value == "—"


@pytest.mark.parametrize(
    "page",
    ["Capital deployment", "Returns", "Provenance", "Integrity", "Methodology"],
)
def test_every_page_renders(page: str, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch):
    app = launch(bundle_dir, monkeypatch, page=page)
    assert not app.exception, f"{page}: {app.exception}"


def test_the_disclaimer_appears_on_every_page(bundle_dir: Path, monkeypatch: pytest.MonkeyPatch):
    for page in ("Overview", "Returns", "Vintage simulator"):
        app = launch(bundle_dir, monkeypatch, page=page)
        captions = " ".join(caption.value for caption in app.caption)
        assert "Not investment, legal, tax or accounting advice" in captions, page


def test_the_integrity_page_reports_a_clean_audit(
    bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    app = launch(bundle_dir, monkeypatch, page="Integrity")
    assert any("traces to evidence" in item.value for item in app.success)


class TestSimulator:
    def test_nothing_runs_before_the_form_is_submitted(
        self, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # A slider drag must not fire a scenario.
        app = launch(bundle_dir, monkeypatch, page="Vintage simulator")
        assert any("Nothing computes until you do" in item.value for item in app.info)
        assert not app.metric

    def test_submitting_produces_a_scenario(
        self, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        app = launch(bundle_dir, monkeypatch, page="Vintage simulator")
        app.button[0].click().run()
        assert not app.exception
        labels = " ".join(metric.label for metric in app.metric)
        assert "Net present value" in labels
        assert "Payback" in labels

    def test_scenario_output_is_marked_as_a_scenario(
        self, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        app = launch(bundle_dir, monkeypatch, page="Vintage simulator")
        app.button[0].click().run()
        labels = " ".join(metric.label for metric in app.metric)
        assert "○" in labels or "!" in labels

    def test_the_what_must_be_true_answer_is_shown(
        self, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        app = launch(bundle_dir, monkeypatch, page="Vintage simulator")
        app.button[0].click().run()
        answers = [item.value for item in app.success] + [item.value for item in app.error]
        assert any("utilization" in answer for answer in answers)

    def test_the_answer_names_its_lever_in_words_not_identifiers(
        self, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        app = launch(bundle_dir, monkeypatch, page="Vintage simulator")
        app.button[0].click().run()
        answers = [item.value for item in app.success] + [item.value for item in app.error]
        joined = " ".join(answers)
        assert "payback_years" not in joined
        assert "payback of" in joined

    def test_the_spend_input_reaches_the_engine_in_dollars(
        self, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """The regression that shipped: the form asked for millions and the
        engine declared the answer in USD, so a $10bn program reported a net
        present value of ``-162.21 USD``. It meant -$162.2M all along.
        """
        app = launch(bundle_dir, monkeypatch, page="Vintage simulator")
        app.button[0].click().run()
        npv = next(m for m in app.metric if "Net present value" in m.label)
        # The default form is 10 billion of spend, so the answer belongs in
        # millions or billions. Anything smaller means the scaling was dropped.
        assert npv.value.endswith(("M", "B")), npv.value


def test_a_missing_bundle_explains_how_to_build_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(sys, "argv", ["app.py", "--bundle", str(tmp_path / "absent")])
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.run()
    assert not app.exception
    assert any("capex-atlas analyze" in item.value for item in app.error)
