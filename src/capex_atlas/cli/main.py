"""Command line.

Thin by design: every command resolves to a call into the library, so the CLI
never becomes the only way to reach a feature. Output goes to stdout as text or
JSON; nothing here does analysis of its own.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Annotated, Any

import typer

from capex_atlas import __version__
from capex_atlas.accounting.reconciliation import CheckStatus, reconcile
from capex_atlas.adapters import adapter_for
from capex_atlas.bundle import (
    AnalysisBundle,
    FactScope,
    audit_bundle,
    build_analysis,
    content_only,
    diff_bundles,
    headline_table,
    read_bundle,
    write_bundle,
)
from capex_atlas.cli.launcher import (
    app_path,
    default_bundle,
    streamlit_available,
)
from capex_atlas.disclaimer import FULL, SHORT
from capex_atlas.schemas.source import SourceReference
from capex_atlas.sources.raw import RawStore
from capex_atlas.sources.sec import SecClient
from capex_atlas.xbrl.companyfacts import extract_facts

app = typer.Typer(
    add_completion=False,
    help=f"Capex Atlas: source-linked models of hyperscaler capital deployment.\n\n{SHORT}",
    no_args_is_help=True,
)

DEFAULT_DATA = Path("data") / "raw"

TickerArg = Annotated[str, typer.Argument(help="Ticker, e.g. GOOGL")]
PeriodOpt = Annotated[str, typer.Option("--through", help="Fiscal period, e.g. 2025FY or 2026Q2")]


def _client(data_dir: Path) -> SecClient:
    return SecClient(store=RawStore(data_dir))


def _load_facts(ticker: str, data_dir: Path) -> tuple[dict[str, Any], SourceReference]:
    with _client(data_dir) as client:
        cik = client.cik_for_ticker(ticker)
        artifact, payload = client.company_facts(cik, ticker)
    return payload, artifact.to_source_reference()


@app.callback()
def _root() -> None:
    """Capex Atlas."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def disclaimer() -> None:
    """Print the full legal disclaimer."""
    typer.echo(FULL)


@app.command()
def ingest(
    ticker: TickerArg,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA,
) -> None:
    """Download a filer's Company Facts into the raw store."""
    payload, source = _load_facts(ticker, data_dir)
    concepts = len(payload.get("facts", {}).get("us-gaap", {}))
    typer.echo(f"{ticker}: {concepts} us-gaap concepts stored under {data_dir}")
    typer.echo(f"source: {source.url}")


@app.command(name="reconcile")
def reconcile_cmd(
    ticker: TickerArg,
    period: PeriodOpt = "2025FY",
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA,
) -> None:
    """Run the accounting identities over a filer's facts."""
    # Resolve by ticker, and do it before touching the network: there is no
    # reason to download a filing for a company we cannot analyze. Hardcoding
    # one adapter here meant `reconcile MSFT` silently applied a December
    # year-end to a June filer.
    adapter = adapter_for(ticker)
    payload, source = _load_facts(ticker, data_dir)
    extraction = extract_facts(
        payload,
        entity_id=ticker,
        calendar=adapter.calendar(),
        source=source,
        statement_map=adapter.statement_map(),
    )
    report = reconcile(
        extraction.facts,
        cumulative_concepts=list(adapter.cumulative_concepts()),
    )
    skipped = sum(1 for r in report.results if r.status is CheckStatus.SKIPPED)
    typer.echo(
        f"{ticker} {period}: {report.verified_count} checks verified, "
        f"{len(report.failures)} failed, {skipped} skipped"
    )
    for failure in report.failures:
        typer.echo(f"  FAIL {failure.check} {failure.period_label}: {failure.detail}")
    if not report.passed:
        raise typer.Exit(1)


@app.command()
def analyze(
    ticker: TickerArg,
    period: PeriodOpt = "2025FY",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA,
    facts: Annotated[
        FactScope,
        typer.Option(
            "--facts",
            help="How much history to carry: used, period, or all. History is most of a "
            "bundle's bytes, so 'used' suits an artifact meant to travel.",
        ),
    ] = FactScope.ALL,
) -> None:
    """Build an analysis bundle and optionally write it out."""
    adapter_for(ticker)  # fail before the download if the filer is not covered
    payload, source = _load_facts(ticker, data_dir)
    bundle = build_analysis(
        payload,
        entity_id=ticker,
        period_label=period,
        source=source,
        facts_scope=facts,
        command=f"analyze {ticker} --through {period} --facts {facts.value}",
    )
    for label, formatted, status in headline_table(bundle):
        typer.echo(f"  {label:<46} {formatted:>24}  {status}")
    typer.echo(f"\n{SHORT}")
    if output is not None:
        written = write_bundle(bundle, output)
        typer.echo(f"\nwrote {written}")


@app.command(name="app")
def launch_app(
    bundle: Annotated[
        Path | None,
        typer.Option("--bundle", help="Bundle to open. Defaults to the shipped example."),
    ] = None,
    port: Annotated[int | None, typer.Option("--port")] = None,
) -> None:
    """Open the reference lab in a browser.

    Exists so installing the app extra is usable without a git checkout:
    the app and the example bundle are both shipped inside the wheel.
    """
    if not streamlit_available():
        typer.echo(
            "the lab needs the app extra: pip install 'capex-atlas[app]'",
            err=True,
        )
        raise typer.Exit(1)

    target = bundle or default_bundle()
    if target is None:
        typer.echo(
            "no bundle to open. Build one first:\n"
            "  capex-atlas analyze GOOGL --through 2025FY -o my-analysis",
            err=True,
        )
        raise typer.Exit(1)

    command = ["streamlit", "run", str(app_path())]
    if port is not None:
        command += ["--server.port", str(port)]
    command += ["--", "--bundle", str(target)]
    typer.echo(f"opening {target}")
    raise typer.Exit(subprocess.call(command))


@app.command()
def audit(
    bundle_path: Annotated[Path, typer.Argument(help="Bundle file or directory")],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check that every value in a bundle traces to evidence.

    The acceptance test for a published analysis. Exits non-zero on any value
    that cannot be traced back to a calculation, a source or a cited assumption.
    """
    bundle = read_bundle(bundle_path)
    report = audit_bundle(bundle)
    if as_json:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(
            f"{bundle.entity_id} {bundle.period_label}: {report.values_checked} values checked, "
            f"{len(report.errors)} errors, {len(report.warnings)} warnings"
        )
        for finding in report.findings:
            typer.echo(f"  {finding}")
    if not report.passed:
        raise typer.Exit(1)


@app.command()
def diff(
    before: Annotated[Path, typer.Argument()],
    after: Annotated[Path, typer.Argument()],
) -> None:
    """Explain what changed between two analyses."""
    result = diff_bundles(read_bundle(before), read_bundle(after))
    if result.identical:
        typer.echo("identical")
        return
    for change in result.changes:
        typer.echo(f"  {change}")


@app.command()
def verify(
    bundle_path: Annotated[Path, typer.Argument()],
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA,
) -> None:
    """Rebuild a bundle from its inputs and confirm it reproduces byte for byte."""
    stored = read_bundle(bundle_path)

    # This command rebuilds from SEC. A bundle produced some other way, such as
    # the committed example built from a pinned fixture, has different inputs and
    # would report a difference that says nothing about reproducibility.
    produced_by = (stored.provenance.command if stored.provenance else None) or "unknown"
    if not produced_by.startswith("analyze"):
        typer.echo(
            f"cannot verify: this bundle was produced by `{produced_by}`, not by `analyze`, "
            "so rebuilding it from SEC would compare different inputs."
        )
        typer.echo("Rebuild it with the command that made it, then compare.")
        raise typer.Exit(2)

    payload, source = _load_facts(stored.entity_id, data_dir)
    rebuilt = build_analysis(
        payload,
        entity_id=stored.entity_id,
        period_label=stored.period_label,
        source=source,
        template=stored.template,
        # Rebuild under the scope the bundle was written with. Defaulting to ALL
        # here meant a bundle built with --facts used could never reproduce, and
        # the command whose job is proving reproducibility always failed on it.
        facts_scope=FactScope(str(stored.notes.get("facts_scope", FactScope.ALL.value))),
    )
    if content_only(stored) == content_only(rebuilt):
        typer.echo("reproduced: content identical")
        return

    typer.echo("DIFFERS from the stored bundle:")
    changes = diff_bundles(stored, rebuilt).changes
    for change in changes:
        typer.echo(f"  {change}")
    if not changes:
        # The diff compares published values, assumptions and restatements. A
        # difference it cannot see is still a difference, so name where it is
        # rather than reporting nothing.
        typer.echo(f"  {_where_they_differ(stored, rebuilt)}")
    raise typer.Exit(1)


def _where_they_differ(stored: AnalysisBundle, rebuilt: AnalysisBundle) -> str:
    """Name the sections that differ when the value diff comes back empty."""
    left = json.loads(content_only(stored))
    right = json.loads(content_only(rebuilt))
    sections = sorted(key for key in left | right if left.get(key) != right.get(key))
    if not sections:
        return "no section differs, which should be impossible; please report this"
    return "sections that differ: " + ", ".join(sections)


app.command(name="reconcile")(reconcile_cmd)
