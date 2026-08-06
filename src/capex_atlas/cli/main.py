"""Command line.

Thin by design: every command resolves to a call into the library, so the CLI
never becomes the only way to reach a feature. Output goes to stdout as text or
JSON; nothing here does analysis of its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from capex_atlas import __version__
from capex_atlas.accounting.reconciliation import CheckStatus, reconcile
from capex_atlas.adapters.alphabet import AlphabetAdapter
from capex_atlas.bundle import (
    FactScope,
    audit_bundle,
    build_analysis,
    content_only,
    diff_bundles,
    headline_table,
    read_bundle,
    write_bundle,
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


@app.command()
def reconcile_cmd(
    ticker: TickerArg,
    period: PeriodOpt = "2025FY",
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA,
) -> None:
    """Run the accounting identities over a filer's facts."""
    payload, source = _load_facts(ticker, data_dir)
    adapter = AlphabetAdapter()
    extraction = extract_facts(
        payload,
        entity_id=ticker,
        calendar=adapter.calendar(),
        source=source,
        statement_map=adapter.statement_map(),
    )
    report = reconcile(
        extraction.facts,
        cumulative_concepts=[
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "NetCashProvidedByUsedInOperatingActivities",
        ],
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
    payload, source = _load_facts(stored.entity_id, data_dir)
    rebuilt = build_analysis(
        payload,
        entity_id=stored.entity_id,
        period_label=stored.period_label,
        source=source,
        template=stored.template,
    )
    if content_only(stored) == content_only(rebuilt):
        typer.echo("reproduced: content identical")
        return
    typer.echo("DIFFERS from the stored bundle:")
    for change in diff_bundles(stored, rebuilt).changes:
        typer.echo(f"  {change}")
    raise typer.Exit(1)


app.command(name="reconcile")(reconcile_cmd)
