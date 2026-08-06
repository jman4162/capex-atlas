"""CLI behaviour, driven against the pinned fixture rather than the network.

``ingest`` is the only command that must reach SEC, so it is exercised through a
mock transport. Everything downstream runs on the fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from capex_atlas.bundle import build_analysis, write_bundle
from capex_atlas.cli.main import app
from capex_atlas.schemas.source import SourceKind, SourceReference

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "googl_companyfacts_trimmed.json"
runner = CliRunner()


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    payload = json.loads(FIXTURE.read_text())
    bundle = build_analysis(
        payload,
        entity_id="GOOGL",
        period_label="2025FY",
        source=SourceReference(
            kind=SourceKind.SEC_FILING,
            url="https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json",
        ),
        command="analyze GOOGL --through 2025FY",
    )
    target = tmp_path / "googl-2025fy"
    write_bundle(bundle, target)
    return target


class TestBasics:
    def test_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert result.stdout.strip()

    def test_disclaimer_is_printable(self):
        result = runner.invoke(app, ["disclaimer"])
        assert result.exit_code == 0
        assert "No liability" in result.stdout

    def test_help_carries_the_short_disclaimer(self):
        result = runner.invoke(app, ["--help"])
        assert "Not investment" in result.stdout


class TestAudit:
    def test_a_sound_bundle_passes(self, bundle_dir: Path):
        result = runner.invoke(app, ["audit", str(bundle_dir)])
        assert result.exit_code == 0
        assert "0 errors" in result.stdout

    def test_json_output_is_machine_readable(self, bundle_dir: Path):
        result = runner.invoke(app, ["audit", str(bundle_dir), "--json"])
        assert result.exit_code == 0
        assert json.loads(result.stdout)["values_checked"] > 0

    def test_a_broken_chain_exits_non_zero(self, bundle_dir: Path, tmp_path: Path):
        # The acceptance test has to actually fail, or a green run means nothing.
        payload = json.loads((bundle_dir / "analysis.atlas.json").read_text())
        payload["values"][0]["source_ids"] = ["src:missing"]
        broken = tmp_path / "broken"
        broken.mkdir()
        (broken / "analysis.atlas.json").write_text(json.dumps(payload))

        result = runner.invoke(app, ["audit", str(broken)])
        assert result.exit_code == 1
        assert "does not carry" in result.stdout

    def test_a_bundle_stripped_of_its_disclaimer_fails(self, bundle_dir: Path, tmp_path: Path):
        payload = json.loads((bundle_dir / "analysis.atlas.json").read_text())
        payload["disclaimer"] = ""
        stripped = tmp_path / "stripped"
        stripped.mkdir()
        (stripped / "analysis.atlas.json").write_text(json.dumps(payload))

        result = runner.invoke(app, ["audit", str(stripped)])
        assert result.exit_code == 1
        assert "disclaimer" in result.stdout


class TestDiff:
    def test_identical_bundles_report_no_change(self, bundle_dir: Path):
        result = runner.invoke(app, ["diff", str(bundle_dir), str(bundle_dir)])
        assert result.exit_code == 0
        assert "identical" in result.stdout

    def test_a_different_period_shows_moved_values(self, bundle_dir: Path, tmp_path: Path):
        payload = json.loads(FIXTURE.read_text())
        earlier = build_analysis(
            payload,
            entity_id="GOOGL",
            period_label="2024FY",
            source=SourceReference(kind=SourceKind.SEC_FILING, url="https://x"),
        )
        other = tmp_path / "googl-2024fy"
        write_bundle(earlier, other)

        result = runner.invoke(app, ["diff", str(other), str(bundle_dir)])
        assert result.exit_code == 0
        assert "value_changed" in result.stdout


def test_the_bundle_directory_carries_its_disclaimer(bundle_dir: Path):
    assert (bundle_dir / "DISCLAIMER.md").exists()
    assert "No liability" in (bundle_dir / "DISCLAIMER.md").read_text()
