"""Reusable pieces of the lab's interface.

Rendering only. Anything that decides what a number *is* belongs in
``capex_atlas.application``; these functions decide how it looks.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from capex_atlas.application import MetricCard, ProvenanceNode
from capex_atlas.capital_vintages.solver import LEVER_TITLES, LEVER_UNITS, SensitivityBand
from capex_atlas.disclaimer import SHORT
from capex_atlas.schemas.decimals import format_compact, format_value
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.source import SourceReference

STATUS_HELP = {
    EvidenceStatus.REPORTED: "Stated by the company in a filing.",
    EvidenceStatus.DERIVED: "Computed from reported values alone.",
    EvidenceStatus.ESTIMATED: "Depends on a judgement the company did not disclose.",
    EvidenceStatus.SCENARIO: "Depends on an assumption you chose. A what-if.",
    EvidenceStatus.UNRESOLVED: "Could not be determined from the available evidence.",
}


def evidence_badge(status: EvidenceStatus) -> str:
    """Glyph and name, so a reader never has to infer a figure's standing."""
    return f"{status.glyph} {status.value}"


def metric_card(card: MetricCard, *, show_formula: bool = False) -> None:
    """One headline figure, compact on its face and exact in its tooltip.

    The formula is off by default. It is the same string the Provenance page
    renders in full, and repeating it under every card in grey monospace wraps
    raggedly and crowds out the figure it is meant to support.
    """
    st.metric(
        label=f"{card.glyph} {card.title}",
        value=card.display,
        help=f"{card.formatted}\n\n{STATUS_HELP[card.status]}",
    )
    caption = [evidence_badge(card.status)]
    if card.period_label:
        caption.append(card.period_label)
    if show_formula and card.formula:
        caption.append(f"`{card.formula}`")
    st.caption(" · ".join(caption))


def card_grid(cards: Sequence[MetricCard], *, columns: int = 3) -> None:
    """Cards laid out in rows, so a wide screen is not mostly whitespace."""
    for row in range(0, len(cards), columns):
        for column, card in zip(st.columns(columns), cards[row : row + columns], strict=False):
            with column:
                metric_card(card)


def status_legend(counts: dict[EvidenceStatus, int]) -> None:
    """How much of what is on screen is measured versus assumed."""
    if not counts:
        return
    ordered = sorted(counts.items(), key=lambda item: item[0].rank)
    st.caption(
        "Evidence mix: "
        + " · ".join(f"{status.glyph} {count} {status.value}" for status, count in ordered)
    )


def provenance_tree(nodes: Sequence[ProvenanceNode]) -> None:
    """A value's lineage, indented by depth, bottoming out in reported facts.

    Calculations show their formula; leaves show the XBRL tag and the period, so
    the last line of any chain is something a company actually filed.
    """
    if not nodes:
        st.info("No calculation graph recorded for this value.")
        return
    for node in nodes:
        indent = "&nbsp;" * (node.depth * 4)
        shown = format_value(node.result, node.unit)
        name = node.concept if node.is_fact else node.metric_id
        detail = node.period_label if node.is_fact else node.formula
        line = f"{indent}{node.status.glyph} **{name}** = {shown}"
        if detail:
            line += f"  \n{indent}<span style='color:#666;font-size:0.85em'>{detail}</span>"
        st.markdown(line, unsafe_allow_html=True)


def source_list(sources: Sequence[SourceReference]) -> None:
    """The filings behind a figure, with enough detail to look them up."""
    if not sources:
        st.warning("No source recorded. Treat this figure with suspicion.")
        return
    for source in sources:
        parts = [part for part in (source.accession, source.form, source.section) if part]
        line = " · ".join(parts) or source.source_id
        if source.url:
            st.markdown(f"- [{line}]({source.url})")
        else:
            st.markdown(f"- {line}")


def sensitivity_line(band: SensitivityBand, *, unit: str = "USD") -> str:
    """One tornado bar as a sentence.

    The raw form printed the enum name and a bare number: ``revenue_yield
    (0.2 to 0.7) moves value by 9,781``, which says neither what the lever is
    nor what the swing is denominated in.
    """
    lever_unit = LEVER_UNITS[band.lever]
    low = format_compact(band.low_input, lever_unit)
    high = format_compact(band.high_input, lever_unit)
    swing = "—" if band.swing is None else format_compact(band.swing, unit)
    return f"**{LEVER_TITLES[band.lever].capitalize()}** · {low} → {high} swings NPV by {swing}"


def assumption_panel(assumption_ids: Sequence[str]) -> None:
    if not assumption_ids:
        return
    st.caption("Assumptions used: " + ", ".join(f"`{item}`" for item in assumption_ids))


def disclaimer_footer() -> None:
    """Shown on every page. A figure that travels without its conditions is the
    failure this project is built to avoid."""
    st.divider()
    st.caption(SHORT)
    st.caption("Amazon and AWS are out of scope; see DISCLOSURE.md in the repository.")
