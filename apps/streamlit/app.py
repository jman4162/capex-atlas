"""Capex Atlas reference lab.

Run with::

    uv run streamlit run apps/streamlit/app.py -- --bundle examples/googl-2025fy

Every page reads from :class:`~capex_atlas.application.AtlasApplication`. No page
computes anything, which is what keeps the front end replaceable and keeps every
figure inside the provenance kernel.

Two deliberate constraints. The app opens a *stored bundle* rather than fetching,
so browsing is offline, instant and reproducible. And a scenario runs only on an
explicit form submission, never on a widget rerun, so nothing expensive or
nondeterministic fires because someone dragged a slider.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

import streamlit as st

from capex_atlas.application import AtlasApplication
from capex_atlas.capital_vintages.model import AssetClassParameters
from capex_atlas.capital_vintages.solver import Lever, Target
from capex_atlas.obs import tracing
from capex_atlas.scenarios.model import ScenarioDefinition
from capex_atlas.schemas.capital import CapitalCategory

sys.path.insert(0, str(Path(__file__).parent))

from components import (
    assumption_panel,
    disclaimer_footer,
    evidence_badge,
    metric_card,
    provenance_tree,
    source_list,
    status_legend,
)

PAGES = (
    "Overview",
    "Capital deployment",
    "Returns",
    "Vintage simulator",
    "Provenance",
    "Integrity",
    "Methodology",
)


def bundle_path() -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--bundle", default="examples/googl-2025fy")
    known, _ = parser.parse_known_args()
    return Path(known.bundle)


@st.cache_resource
def load(path: str) -> AtlasApplication:
    """Bundles are immutable, so one load per path is enough."""
    tracing.configure()
    return AtlasApplication.from_path(Path(path))


def main() -> None:
    st.set_page_config(page_title="Capex Atlas", layout="wide")
    path = bundle_path()
    if not path.exists():
        st.error(
            f"No bundle at {path}. Build one first:\n\n"
            "```\ncapex-atlas analyze GOOGL --through 2025FY -o examples/googl-2025fy\n```"
        )
        return

    app = load(str(path))
    st.sidebar.title("Capex Atlas")
    st.sidebar.caption(f"{app.bundle.entity_id} · {app.bundle.period_label}")
    page = st.sidebar.radio("Page", PAGES, label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.caption(app.validation_summary)

    with tracing.span("capex_atlas.ui.interaction", **{"capex_atlas.ui.page": str(page)}):
        _render(page, app)
    disclaimer_footer()


def _render(page: str, app: AtlasApplication) -> None:
    if page == "Overview":
        _overview(app)
    elif page == "Capital deployment":
        _capital(app)
    elif page == "Returns":
        _returns(app)
    elif page == "Vintage simulator":
        _simulator(app)
    elif page == "Provenance":
        _provenance(app)
    elif page == "Integrity":
        _integrity(app)
    else:
        _methodology(app)


def _overview(app: AtlasApplication) -> None:
    st.title(f"{app.bundle.entity_id} · {app.bundle.period_label}")
    status_legend(app.evidence_mix())
    cards = app.overview()
    for row in range(0, len(cards), 3):
        for column, card in zip(st.columns(3), cards[row : row + 3], strict=False):
            with column:
                metric_card(card)


def _capital(app: AtlasApplication) -> None:
    st.title("Capital deployment")
    st.caption(
        "Cash spending against the depreciation of the existing base. Above one means "
        "the asset base is growing in nominal terms."
    )
    for label in ("capex to depreciation", "net investment in fixed assets", "capex intensity"):
        card = app.card(label)
        if card:
            metric_card(card)

    concept = st.selectbox("Series", app.concepts(), index=None, placeholder="Pick a concept")
    if concept:
        points = app.series(concept, kind="FY")
        if points:
            st.bar_chart(
                {"value": [float(point.value) for point in points]},
                x_label="fiscal year",
                y_label=concept,
            )
            st.caption(
                "Annual periods only. Mixing quarters with year-to-date figures on one "
                "axis produces a sawtooth that looks like a business collapsing four "
                "times a year."
            )
        else:
            st.info(f"No annual periods tagged for {concept}.")


def _returns(app: AtlasApplication) -> None:
    st.title("Returns")
    st.warning(
        "There is no single correct return on invested capital. Both figures below are "
        "defensible and they differ materially, which is the point of showing them "
        "together rather than picking one."
    )
    for label in (
        "return on invested capital (operating basis)",
        "return on invested capital (excluding cash)",
        "net operating profit after tax",
    ):
        card = app.card(label)
        if card:
            metric_card(card)
            assumption_panel(card.assumption_ids)


def _simulator(app: AtlasApplication) -> None:
    st.title("Vintage simulator")
    st.caption(
        "What would have to be true for a claim to hold? Nothing here is measured; "
        "every output is a scenario."
    )

    with st.form("scenario"):
        spend = st.number_input("Server spend (USD millions)", value=10_000, step=500)
        life = st.number_input("Useful life (years)", value=6, min_value=1, max_value=40)
        lead = st.number_input("Lead time (years)", value=0, min_value=0, max_value=10)
        yield_rate = st.slider("Revenue per unit of capital, at full utilization", 0.05, 1.0, 0.45)
        margin = st.slider("Cash operating margin", 0.05, 0.95, 0.55)
        utilization = st.slider("Steady-state utilization", 0.05, 1.0, 0.85)
        payback_target = st.number_input("Payback claim to test (years)", value=3, min_value=1)
        submitted = st.form_submit_button("Run scenario")

    if not submitted:
        st.info("Set the assumptions, then run. Nothing computes until you do.")
        return

    definition = ScenarioDefinition(
        scenario_id="interactive",
        name="Interactive",
        description="Parameters set in the lab",
        asset_classes=(
            AssetClassParameters(
                asset_class=CapitalCategory.SERVERS,
                spend=Decimal(str(spend)),
                lead_time_years=Decimal(str(lead)),
                useful_life_years=Decimal(str(life)),
                utilization_ramp=(Decimal(str(utilization)),),
                revenue_yield=Decimal(str(yield_rate)),
                operating_margin=Decimal(str(margin)),
            ),
        ),
        tax_rate=Decimal("0.21"),
        discount_rate=Decimal("0.09"),
        horizon_years=int(life) + int(lead) + 1,
    )
    result = app.run_scenario(
        definition,
        requirements=(
            (
                Lever.UTILIZATION,
                Target.PAYBACK_YEARS,
                Decimal(str(payback_target)),
                Decimal("0.05"),
                Decimal("1"),
            ),
        ),
        sensitivities={
            Lever.REVENUE_YIELD: (Decimal("0.2"), Decimal("0.7")),
            Lever.OPERATING_MARGIN: (Decimal("0.35"), Decimal("0.75")),
        },
    )

    left, middle, right = st.columns(3)
    left.metric(f"{result.npv.status.glyph} Net present value", result.npv.formatted)
    middle.metric(f"{result.irr.status.glyph} Internal rate of return", result.irr.formatted)
    right.metric(f"{result.payback.status.glyph} Payback", result.payback.formatted)
    st.caption(evidence_badge(result.status))

    st.subheader("What must be true")
    for requirement in result.requirements:
        if requirement.achievable:
            st.success(requirement.description)
        else:
            st.error(requirement.description)

    st.subheader("What the answer rests on")
    for band in result.sensitivities:
        swing = "—" if band.swing is None else f"{band.swing:,.0f}"
        st.write(f"**{band.lever}** ({band.low_input} to {band.high_input}) moves value by {swing}")

    st.subheader("Cash flow by year")
    st.bar_chart({"free cash flow": [float(y.free_cash_flow) for y in result.schedule.years]})


def _provenance(app: AtlasApplication) -> None:
    st.title("Provenance")
    st.caption("Pick a figure and see the formula, the inputs and the filings beneath it.")
    labels = [card.label for card in app.overview()]
    chosen = st.selectbox("Value", labels)
    if not chosen:
        return
    card = app.card(chosen)
    if card:
        metric_card(card)
    st.subheader("Calculation")
    provenance_tree(app.lineage(chosen))
    st.subheader("Sources")
    source_list(app.sources_for(chosen))


def _integrity(app: AtlasApplication) -> None:
    st.title("Integrity")
    report = app.audit()
    if report.passed:
        st.success(f"{report.values_checked} values checked; every one traces to evidence.")
    else:
        st.error(f"{len(report.errors)} values cannot be traced to evidence.")
    for finding in report.findings:
        (st.error if finding.severity.value == "error" else st.warning)(str(finding))
    st.caption(app.validation_summary)
    notes = app.bundle.notes
    if notes:
        st.subheader("Extraction notes")
        st.json(notes)


def _methodology(app: AtlasApplication) -> None:
    st.title("Methodology")
    st.markdown(
        """
Every figure carries one of five statuses, and a calculation always takes the
weakest of its inputs.

| glyph | status | meaning |
|---|---|---|
| ● | reported | Stated by the company in a filing. |
| ◆ | derived | Computed from reported values alone. |
| ▲ | estimated | Depends on a judgement the company did not disclose. |
| ○ | scenario | Depends on an assumption you chose. |
| ! | unresolved | Could not be determined from the evidence. |

A calculation is never itself *reported*, however solid its inputs. A calculation
touching anything undetermined comes out undetermined rather than defaulting to
zero, because a missing input and a zero input are different claims.
        """
    )
    if app.bundle.assumptions:
        st.subheader("Assumptions in this bundle")
        for assumption in app.bundle.assumptions:
            st.markdown(
                f"- `{assumption.assumption_id}` = {assumption.value} "
                f"({assumption.basis.value} → {assumption.status.glyph} "
                f"{assumption.status.value})"
            )
            if assumption.citation and assumption.citation.quote:
                st.caption(f"  > {assumption.citation.quote}")


if __name__ == "__main__":
    main()
