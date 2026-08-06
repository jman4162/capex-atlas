"""Turning SEC Company Facts JSON into normalized facts.

Two traps live in this file, and both produce numbers that look right.

The first is the ``fy``/``fp`` fields. They describe the *filing* that reported a
value rather than the span the value covers. A 10-K for fiscal 2026 carries
prior-year comparatives all tagged ``fy: 2026, fp: FY``, so trusting those fields
silently shifts several years of history forward. The period here always comes
from the ``start``/``end`` dates instead.

The second is duplication. The same concept and period appear in every filing
that shows them as a comparative, sometimes with different values after a
restatement. Keeping the latest filing is right; keeping it quietly is not, so
disagreements are reported rather than dropped.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from capex_atlas.normalization.calendar import FiscalCalendar
from capex_atlas.schemas.facts import FinancialFact, Statement
from capex_atlas.schemas.period import FiscalPeriod
from capex_atlas.schemas.source import SourceReference

DEFAULT_TAXONOMIES = ("us-gaap",)


class Restatement(BaseModel):
    """The same concept and period reported twice with different values."""

    model_config = ConfigDict(frozen=True)

    concept: str
    period_label: str
    unit: str
    superseded_value: Decimal
    current_value: Decimal
    superseded_accession: str | None
    current_accession: str | None

    @property
    def difference(self) -> Decimal:
        return self.current_value - self.superseded_value


class SkippedEntry(BaseModel):
    """An entry that could not be placed on the fiscal calendar."""

    model_config = ConfigDict(frozen=True)

    concept: str
    start: date | None
    end: date
    reason: str


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    facts: tuple[FinancialFact, ...]
    restatements: tuple[Restatement, ...]
    skipped: tuple[SkippedEntry, ...]

    def by_concept(self, concept: str) -> list[FinancialFact]:
        return [f for f in self.facts if f.xbrl_concept == concept]


def extract_facts(
    payload: dict[str, Any],
    *,
    entity_id: str,
    calendar: FiscalCalendar,
    source: SourceReference,
    statement_map: dict[str, Statement],
    taxonomies: tuple[str, ...] = DEFAULT_TAXONOMIES,
) -> ExtractionResult:
    """Read a Company Facts payload into :class:`FinancialFact` rows.

    Only concepts present in *statement_map* are extracted. An allow-list rather
    than a sweep, because a fact nobody has classified onto a statement cannot be
    reconciled and would sit in the dataset unverified.
    """
    chosen: dict[tuple[str, str, str], tuple[str, dict[str, Any], FiscalPeriod]] = {}
    restatements: list[Restatement] = []
    skipped: list[SkippedEntry] = []

    for taxonomy in taxonomies:
        concepts: dict[str, Any] = payload.get("facts", {}).get(taxonomy, {})
        for concept, body in concepts.items():
            if concept not in statement_map:
                continue
            for unit, entries in body.get("units", {}).items():
                for entry in entries:
                    _consider(
                        concept=concept,
                        unit=unit,
                        entry=entry,
                        calendar=calendar,
                        chosen=chosen,
                        restatements=restatements,
                        skipped=skipped,
                    )

    facts = tuple(
        _build_fact(
            concept=concept,
            unit=unit,
            entry=entry,
            # Carry the period object through rather than re-parsing its label:
            # the label alone drops start and end, and the reconciliation layer
            # needs the real dates.
            period=period,
            entity_id=entity_id,
            source=source,
            statement=statement_map[concept],
        )
        for (concept, unit, _label), (_, entry, period) in sorted(chosen.items())
    )
    return ExtractionResult(
        facts=facts,
        restatements=tuple(restatements),
        skipped=tuple(skipped),
    )


def _consider(
    *,
    concept: str,
    unit: str,
    entry: dict[str, Any],
    calendar: FiscalCalendar,
    chosen: dict[tuple[str, str, str], tuple[str, dict[str, Any], FiscalPeriod]],
    restatements: list[Restatement],
    skipped: list[SkippedEntry],
) -> None:
    end = date.fromisoformat(entry["end"])
    start = date.fromisoformat(entry["start"]) if entry.get("start") else None

    period = calendar.period_for(start, end)
    if period is None:
        # Only duration facts reach here; instants always classify.
        span = f"{(end - start).days + 1} day" if start is not None else "unknown"
        skipped.append(
            SkippedEntry(
                concept=concept,
                start=start,
                end=end,
                reason=f"{span} span matches no standard period",
            )
        )
        return

    key = (concept, unit, period.label)
    filed = str(entry.get("filed", ""))
    incumbent = chosen.get(key)

    if incumbent is None:
        chosen[key] = (filed, entry, period)
        return

    incumbent_filed, incumbent_entry, _ = incumbent
    if filed <= incumbent_filed:
        return

    if Decimal(str(incumbent_entry["val"])) != Decimal(str(entry["val"])):
        restatements.append(
            Restatement(
                concept=concept,
                period_label=period.label,
                unit=unit,
                superseded_value=Decimal(str(incumbent_entry["val"])),
                current_value=Decimal(str(entry["val"])),
                superseded_accession=incumbent_entry.get("accn"),
                current_accession=entry.get("accn"),
            )
        )
    chosen[key] = (filed, entry, period)


def _build_fact(
    *,
    concept: str,
    unit: str,
    entry: dict[str, Any],
    period: FiscalPeriod,
    entity_id: str,
    source: SourceReference,
    statement: Statement,
) -> FinancialFact:
    accession = entry.get("accn")
    # narrow(), not model_copy(): the id has to be rebuilt from the new fields,
    # or facts drawn from different filings would all cite the same place.
    citation = source.narrow(
        accession=accession or source.accession,
        form=entry.get("form") or source.form,
        section=f"XBRL {concept} ({period.label})",
    )
    return FinancialFact(
        entity_id=entity_id,
        metric_id=concept,
        value=Decimal(str(entry["val"])),
        unit=unit,
        period=period,
        statement=statement,
        source=citation,
        xbrl_concept=concept,
        extraction_method="sec_companyfacts",
    )
