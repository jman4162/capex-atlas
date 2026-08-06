"""Reusable pieces of the lab's interface.

Rendering only. Anything that decides what a number *is* belongs in
``capex_atlas.application``; these functions decide how it looks.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from capex_atlas.application import MetricCard, ProvenanceNode
from capex_atlas.disclaimer import SHORT
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


def metric_card(card: MetricCard) -> None:
    """One headline figure with its standing and formula visible, not hidden."""
    st.metric(
        label=f"{card.glyph} {card.label}",
        value=card.formatted,
        help=STATUS_HELP[card.status],
    )
    caption = [evidence_badge(card.status)]
    if card.period_label:
        caption.append(card.period_label)
    if card.formula:
        caption.append(f"`{card.formula}`")
    st.caption(" · ".join(caption))


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
    """A value's lineage, indented by depth."""
    if not nodes:
        st.info("No calculation graph recorded for this value.")
        return
    for node in nodes:
        indent = "&nbsp;" * (node.depth * 4)
        shown = "—" if node.result is None else f"{node.result:,f}"
        st.markdown(
            f"{indent}{node.status.glyph} **{node.metric_id}** = {shown} {node.unit}  \n"
            f"{indent}<span style='color:#666;font-size:0.85em'>{node.formula}</span>",
            unsafe_allow_html=True,
        )


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
