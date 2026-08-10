"""Regressions for the three bugs the v0.1.0 audit found.

Each of these shipped in a tagged release. They are pinned here because the
command that proves reproducibility failing silently is the worst class of bug
this project can have.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from capex_atlas.bundle import FactScope, build_analysis, content_only, write_bundle
from capex_atlas.bundle.audit import audit_bundle
from capex_atlas.cli import main as cli
from capex_atlas.cli.main import app
from capex_atlas.schemas.period import PeriodKind
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

    def fake_client(data_dir: Path, **policy: object) -> SecClient:
        return SecClient(
            store=RawStore(data_dir),
            user_agent=AGENT,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            **policy,  # type: ignore[arg-type]
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


class TestTheCommandsThatReachSec:
    """`analyze`, `ingest` and `reconcile` had no test coverage at all.

    All three run here against the pinned fixture through a mocked transport, so
    the bodies execute without touching the network.
    """

    def test_ingest_reports_what_it_stored(self, offline_sec: None, tmp_path: Path):
        result = runner.invoke(app, ["ingest", "GOOGL", "--data-dir", str(tmp_path / "data")])
        assert result.exit_code == 0, result.output
        assert "us-gaap concepts stored" in result.stdout
        assert (tmp_path / "data").exists()

    def test_analyze_prints_a_headline_table_with_status(self, offline_sec: None, tmp_path: Path):
        result = runner.invoke(
            app, ["analyze", "GOOGL", "--through", "2025FY", "--data-dir", str(tmp_path / "data")]
        )
        assert result.exit_code == 0, result.output
        assert "free cash flow (reported basis)" in result.stdout
        assert "derived" in result.stdout
        # Every run carries the short disclaimer.
        assert "Not investment" in result.stdout

    def test_analyze_writes_a_bundle_that_audits(self, offline_sec: None, tmp_path: Path):
        target = tmp_path / "out"
        built = runner.invoke(
            app,
            [
                "analyze",
                "GOOGL",
                "--through",
                "2025FY",
                "-o",
                str(target),
                "--data-dir",
                str(tmp_path / "data"),
            ],
        )
        assert built.exit_code == 0, built.output
        audited = runner.invoke(app, ["audit", str(target)])
        assert audited.exit_code == 0, audited.output

    def test_reconcile_runs_the_identities(self, offline_sec: None, tmp_path: Path):
        result = runner.invoke(app, ["reconcile", "GOOGL", "--data-dir", str(tmp_path / "data")])
        assert result.exit_code == 0, result.output
        assert "checks verified" in result.stdout

    def test_reconcile_runs_the_year_to_date_checks_it_advertises(
        self, offline_sec: None, tmp_path: Path
    ):
        """The command passed canonical concept names to a matcher keyed on XBRL
        tags, so the whole quarterly family matched nothing and was reported as
        skipped -- with a message blaming absent data for a naming mismatch.

        Asserting only "checks verified" was what let it through, so this counts.
        """
        result = runner.invoke(app, ["reconcile", "GOOGL", "--data-dir", str(tmp_path / "data")])
        assert result.exit_code == 0, result.output
        assert "34 checks verified" in result.stdout
        assert "0 skipped" in result.stdout

    def test_reconcile_no_longer_takes_a_period_it_ignores(self, offline_sec: None, tmp_path: Path):
        # --through was echoed and never used; it accepted `banana`.
        result = runner.invoke(
            app,
            ["reconcile", "GOOGL", "--through", "2025FY", "--data-dir", str(tmp_path / "data")],
        )
        assert result.exit_code != 0


class TestTheAppCommand:
    """`pip install "capex-atlas[app]"` was unusable: no launcher, and the lab
    and example were not in the wheel."""

    def test_it_refuses_clearly_when_the_extra_is_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cli, "streamlit_available", lambda: False)
        result = runner.invoke(app, ["app"])
        assert result.exit_code == 1
        # The guidance goes to stderr, so read the combined output.
        assert "app extra" in result.output

    def test_it_finds_the_shipped_example_by_default(self):
        from capex_atlas.cli.launcher import default_bundle

        bundle = default_bundle()
        assert bundle is not None
        assert (bundle / "analysis.atlas.json").exists()

    def test_it_launches_streamlit_with_the_bundle(self, monkeypatch: pytest.MonkeyPatch):
        seen: dict[str, list[str]] = {}

        def fake_call(command: list[str]) -> int:
            seen["command"] = command
            return 0

        monkeypatch.setattr(cli, "streamlit_available", lambda: True)
        monkeypatch.setattr(cli.subprocess, "call", fake_call)
        result = runner.invoke(app, ["app", "--bundle", "examples/googl-2025fy"])
        assert result.exit_code == 0
        assert seen["command"][:2] == ["streamlit", "run"]
        assert "--bundle" in seen["command"]


class TestTheAnnualScope:
    """History without the quarters.

    The charts plot annual periods only, so carrying every quarterly fact
    tripled the example for nothing drawn. 'annual' is the scope that matches
    what a bundle's charts actually consume.
    """

    @staticmethod
    def scoped(scope: FactScope):  # type: ignore[no-untyped-def]
        return build_analysis(
            json.loads(FIXTURE.read_text()),
            entity_id="GOOGL",
            period_label="2025FY",
            source=SourceReference(kind=SourceKind.SEC_FILING, url="https://x"),
            facts_scope=scope,
        )

    def test_it_keeps_no_quarterly_facts(self):
        kinds = {fact.period.kind for fact in self.scoped(FactScope.ANNUAL).facts}
        assert kinds <= {PeriodKind.FISCAL_YEAR, PeriodKind.INSTANT}

    def test_it_keeps_balance_sheet_dates(self):
        # Instants have no duration, so a naive 'annual' filter would drop
        # invested capital out of the history entirely.
        kinds = {fact.period.kind for fact in self.scoped(FactScope.ANNUAL).facts}
        assert PeriodKind.INSTANT in kinds

    def test_it_sits_between_period_and_all(self):
        counts = {
            scope: len(self.scoped(scope).facts)
            for scope in (FactScope.PERIOD, FactScope.ANNUAL, FactScope.ALL)
        }
        assert counts[FactScope.PERIOD] < counts[FactScope.ANNUAL] < counts[FactScope.ALL]

    def test_it_still_carries_several_years(self):
        years = {fact.period.fiscal_year for fact in self.scoped(FactScope.ANNUAL).facts}
        assert len(years) >= 3, "a chart needs a run of periods to draw a line"


class TestCorruptInputsCannotBePublished:
    """Reconciliation ran, embedded its report, and changed nothing.

    Adding a trillion to every Assets entry produced fourteen failed balance
    sheet identities, moved published invested capital by the same trillion, and
    still audited clean, because nothing read the report the bundle carried.
    """

    @staticmethod
    def corrupted_payload() -> dict[str, object]:
        payload = json.loads(FIXTURE.read_text())
        for entry in payload["facts"]["us-gaap"]["Assets"]["units"]["USD"]:
            entry["val"] = entry["val"] + 1_000_000_000_000
        return payload

    def built(self):  # type: ignore[no-untyped-def]
        return build_analysis(
            self.corrupted_payload(),
            entity_id="GOOGL",
            period_label="2025FY",
            source=SourceReference(kind=SourceKind.SEC_FILING, url="https://x"),
        )

    def test_the_corruption_is_detected_by_reconciliation(self):
        report = self.built().validation
        assert report is not None
        assert not report.passed
        assert report.failures

    def test_it_reaches_a_published_figure(self):
        # Not only "the report is ignored": the bad fact is in the output.
        capital = self.built().value("invested capital (operating basis)")
        assert capital is not None
        assert capital.value is not None
        assert capital.value > Decimal("1e12")

    def test_the_audit_now_fails_it(self):
        report = audit_bundle(self.built())
        assert not report.passed
        assert any("accounting identity failed" in error.problem for error in report.errors)

    def test_a_clean_bundle_still_passes(self):
        clean = build_analysis(
            json.loads(FIXTURE.read_text()),
            entity_id="GOOGL",
            period_label="2025FY",
            source=SourceReference(kind=SourceKind.SEC_FILING, url="https://x"),
        )
        assert audit_bundle(clean).passed


def test_an_unavailable_period_says_which_ones_exist(offline_sec: None, tmp_path: Path):
    """It surfaced as `UnitMismatchError: fcf.reported: unit=INHERIT needs at
    least one analytical input` -- true, and three layers from the mistake."""
    result = runner.invoke(
        app, ["analyze", "GOOGL", "--through", "1999Q9", "--data-dir", str(tmp_path / "data")]
    )
    assert result.exit_code != 0
    message = f"{result.output}{result.exception}"
    assert "not among the periods this filer reports" in message
    assert "2025FY" in message
    assert "UnitMismatchError" not in message


def test_restatements_keep_enough_detail_to_review(offline_sec: None, tmp_path: Path):
    """A count told a reader that something was restated and nothing else."""
    bundle = build_analysis(
        json.loads(FIXTURE.read_text()),
        entity_id="GOOGL",
        period_label="2025FY",
        source=SourceReference(kind=SourceKind.SEC_FILING, url="https://x"),
    )
    restatements = bundle.notes["restatements"]
    assert isinstance(restatements, list) and restatements
    first = restatements[0]
    assert set(first) >= {"concept", "period", "superseded", "current", "current_accession"}
