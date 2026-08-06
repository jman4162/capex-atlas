"""Regressions for the three bugs the v0.1.0 audit found.

Each of these shipped in a tagged release. They are pinned here because the
command that proves reproducibility failing silently is the worst class of bug
this project can have.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from capex_atlas.bundle import FactScope, build_analysis, content_only, write_bundle
from capex_atlas.cli import main as cli
from capex_atlas.cli.main import app
from capex_atlas.schemas.source import SourceKind, SourceReference
from capex_atlas.sources.raw import RawStore
from capex_atlas.sources.sec import SecClient

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "googl_companyfacts_trimmed.json"
runner = CliRunner()

AGENT = "Capex Atlas tests (tests@example.invalid)"


@pytest.fixture
def offline_sec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Serve the pinned fixture in place of SEC, so the CLI runs offline."""
    payload = json.loads(FIXTURE.read_text())
    index = {
        "0": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
        # A real filer with no adapter, to prove the refusal is about coverage
        # rather than about the ticker being unknown to SEC.
        "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers" in str(request.url):
            return httpx.Response(200, json=index)
        return httpx.Response(200, json=payload)

    def fake_client(data_dir: Path) -> SecClient:
        return SecClient(
            store=RawStore(data_dir),
            user_agent=AGENT,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(cli, "_client", fake_client)


@pytest.mark.parametrize("scope", ["used", "period", "all"])
def test_a_bundle_reproduces_under_every_fact_scope(scope: str, offline_sec: None, tmp_path: Path):
    """`verify` dropped facts_scope, so anything but `all` could never reproduce.

    The README documented `--facts used` and `verify` on consecutive lines.
    """
    target = tmp_path / scope
    built = runner.invoke(
        app,
        [
            "analyze",
            "GOOGL",
            "--through",
            "2025FY",
            "--facts",
            scope,
            "-o",
            str(target),
            "--data-dir",
            str(tmp_path / "data"),
        ],
    )
    assert built.exit_code == 0, built.output

    verified = runner.invoke(app, ["verify", str(target), "--data-dir", str(tmp_path / "data")])
    assert verified.exit_code == 0, verified.output
    assert "reproduced" in verified.stdout


def test_verify_refuses_a_bundle_it_did_not_build(tmp_path: Path):
    """A fixture-built bundle has different inputs; saying DIFFERS would mislead."""
    bundle = build_analysis(
        json.loads(FIXTURE.read_text()),
        entity_id="GOOGL",
        period_label="2025FY",
        source=SourceReference(kind=SourceKind.SEC_FILING, url="https://x"),
        facts_scope=FactScope.PERIOD,
        command="python scripts/build_example.py",
    )
    target = tmp_path / "example"
    write_bundle(bundle, target)

    result = runner.invoke(app, ["verify", str(target)])
    assert result.exit_code == 2
    assert "not by `analyze`" in result.stdout


def test_verify_names_the_sections_when_the_value_diff_is_empty(tmp_path: Path):
    """Reporting DIFFERS with nothing listed tells a reader nothing."""
    payload = json.loads(FIXTURE.read_text())
    source = SourceReference(kind=SourceKind.SEC_FILING, url="https://x")
    wide = build_analysis(
        payload,
        entity_id="GOOGL",
        period_label="2025FY",
        source=source,
        facts_scope=FactScope.ALL,
    )
    narrow = build_analysis(
        payload,
        entity_id="GOOGL",
        period_label="2025FY",
        source=source,
        facts_scope=FactScope.USED,
    )
    # Same published values, different fact payloads.
    assert content_only(wide) != content_only(narrow)
    sections = cli._where_they_differ(wide, narrow)
    assert "facts" in sections


def test_help_lists_reconcile_once():
    """Typer derived a second name from the function, so it appeared twice."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "reconcile-cmd" not in result.stdout
    assert result.stdout.count("reconcile") == 1


def test_reconcile_refuses_a_filer_with_no_adapter(offline_sec: None, tmp_path: Path):
    """It hardcoded Alphabet, so any other filer got a December year-end."""
    result = runner.invoke(app, ["reconcile", "AAPL", "--data-dir", str(tmp_path / "data")])
    assert result.exit_code != 0
    assert "no adapter" in f"{result.output}{result.exception}"


def test_an_uncovered_filer_fails_before_the_download(offline_sec: None, tmp_path: Path):
    """No reason to pull a filing for a company we cannot analyze."""
    result = runner.invoke(app, ["analyze", "AAPL", "--data-dir", str(tmp_path / "data")])
    assert result.exit_code != 0
    assert not (tmp_path / "data").exists(), "downloaded before checking coverage"
