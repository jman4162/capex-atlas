"""Finding the lab and the example, from a wheel or from a checkout.

`pip install "capex-atlas[app]"` used to install Streamlit and leave the user
with no way to start it and nothing to open. These paths are what fixed that, so
they are worth pinning.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from capex_atlas.cli import launcher


class TestFromACheckout:
    def test_the_app_is_found(self):
        assert launcher.app_path().name == "app.py"

    def test_the_examples_directory_is_found(self):
        directory = launcher.examples_dir()
        assert directory is not None and directory.is_dir()

    def test_the_default_bundle_is_the_committed_example(self):
        bundle = launcher.default_bundle()
        assert bundle is not None
        assert bundle.name == "googl-2025fy"
        assert (bundle / "analysis.atlas.json").exists()


class TestTheBundledCopyWins:
    """A wheel install has no checkout beside it, so the packaged copy is used."""

    def test_the_bundled_app_is_preferred(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        bundled = tmp_path / "_app" / "app.py"
        bundled.parent.mkdir()
        bundled.write_text("")
        monkeypatch.setattr(launcher, "BUNDLED_APP", bundled)
        assert launcher.app_path() == bundled

    def test_the_bundled_examples_are_preferred(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        bundled = tmp_path / "_examples"
        bundled.mkdir()
        monkeypatch.setattr(launcher, "BUNDLED_EXAMPLES", bundled)
        assert launcher.examples_dir() == bundled


class TestWhenNothingIsThere:
    def test_a_missing_app_explains_the_fix(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setattr(launcher, "BUNDLED_APP", tmp_path / "absent.py")
        monkeypatch.setattr(launcher, "CHECKOUT_APP", tmp_path / "also-absent.py")
        with pytest.raises(launcher.AppNotInstalledError, match="capex-atlas\\[app\\]"):
            launcher.app_path()

    def test_no_examples_directory_yields_no_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(launcher, "BUNDLED_EXAMPLES", tmp_path / "absent")
        monkeypatch.setattr(launcher, "CHECKOUT_EXAMPLES", tmp_path / "also-absent")
        assert launcher.examples_dir() is None
        assert launcher.default_bundle() is None

    def test_an_empty_examples_directory_yields_no_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        empty = tmp_path / "_examples"
        empty.mkdir()
        monkeypatch.setattr(launcher, "BUNDLED_EXAMPLES", empty)
        assert launcher.default_bundle() is None

    def test_any_bundle_serves_when_the_named_default_is_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        directory = tmp_path / "_examples"
        other = directory / "msft-2026fy"
        other.mkdir(parents=True)
        (other / "analysis.atlas.json").write_text(json.dumps({}))
        monkeypatch.setattr(launcher, "BUNDLED_EXAMPLES", directory)
        assert launcher.default_bundle() == other


def test_streamlit_availability_is_reported_honestly():
    # The dev group installs it, so this is True here and False for a library-only
    # install. Either way the answer drives a clear message rather than a crash.
    assert launcher.streamlit_available() is True
