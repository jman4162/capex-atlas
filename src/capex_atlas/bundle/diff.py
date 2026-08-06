"""Comparing two bundles.

The point of freezing an analysis is being able to say what changed when it
changes. A restated filing, a revised assumption and a bumped metric version all
move a published number, and they are different stories. The diff separates them
rather than reporting that the figure moved.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from capex_atlas.bundle.model import AnalysisBundle


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    VALUE_CHANGED = "value_changed"
    STATUS_CHANGED = "status_changed"
    FORMULA_CHANGED = "formula_changed"
    ASSUMPTION_CHANGED = "assumption_changed"
    FACT_RESTATED = "fact_restated"


class Change(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ChangeKind
    subject: str
    before: str | None = None
    after: str | None = None
    explanation: str = ""

    def __str__(self) -> str:
        arrow = f"{self.before} -> {self.after}" if self.before is not None else str(self.after)
        suffix = f" ({self.explanation})" if self.explanation else ""
        return f"{self.kind.value}: {self.subject}: {arrow}{suffix}"


class BundleDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    changes: tuple[Change, ...]

    @property
    def identical(self) -> bool:
        return not self.changes

    def of_kind(self, kind: ChangeKind) -> tuple[Change, ...]:
        return tuple(change for change in self.changes if change.kind is kind)


def diff_bundles(before: AnalysisBundle, after: AnalysisBundle) -> BundleDiff:
    """Report what moved between two analyses, and as far as possible why."""
    changes: list[Change] = []
    changes.extend(_diff_values(before, after))
    changes.extend(_diff_assumptions(before, after))
    changes.extend(_diff_facts(before, after))
    return BundleDiff(changes=tuple(changes))


def _label(value: object) -> str:
    from capex_atlas.schemas.values import AnalyticalValue

    assert isinstance(value, AnalyticalValue)
    return value.label or value.value_id


def _diff_values(before: AnalysisBundle, after: AnalysisBundle) -> list[Change]:
    changes: list[Change] = []
    old = {_label(v): v for v in before.values}
    new = {_label(v): v for v in after.values}

    for name in sorted(set(old) - set(new)):
        changes.append(Change(kind=ChangeKind.REMOVED, subject=name, before=str(old[name].value)))
    for name in sorted(set(new) - set(old)):
        changes.append(Change(kind=ChangeKind.ADDED, subject=name, after=str(new[name].value)))

    for name in sorted(set(old) & set(new)):
        previous, current = old[name], new[name]
        if previous.value != current.value:
            changes.append(
                Change(
                    kind=ChangeKind.VALUE_CHANGED,
                    subject=name,
                    before=str(previous.value),
                    after=str(current.value),
                    explanation=_why(before, after, previous, current),
                )
            )
        if previous.status is not current.status:
            changes.append(
                Change(
                    kind=ChangeKind.STATUS_CHANGED,
                    subject=name,
                    before=previous.status.value,
                    after=current.status.value,
                )
            )
    return changes


def _why(before: AnalysisBundle, after: AnalysisBundle, previous: object, current: object) -> str:
    """Attribute a changed number to a formula change where one is visible."""
    from capex_atlas.schemas.values import AnalyticalValue

    assert isinstance(previous, AnalyticalValue) and isinstance(current, AnalyticalValue)
    if previous.formula_node_id is None or current.formula_node_id is None:
        return ""
    old_node = before.node(previous.formula_node_id)
    new_node = after.node(current.formula_node_id)
    if old_node is None or new_node is None:
        return ""
    if old_node.metric_version != new_node.metric_version:
        return f"metric version {old_node.metric_version} -> {new_node.metric_version}"
    if old_node.formula != new_node.formula:
        return "formula text changed"
    return "inputs changed"


def _diff_assumptions(before: AnalysisBundle, after: AnalysisBundle) -> list[Change]:
    old = {a.assumption_id: a for a in before.assumptions}
    new = {a.assumption_id: a for a in after.assumptions}
    changes: list[Change] = []
    for name in sorted(set(old) & set(new)):
        if old[name].value != new[name].value:
            changes.append(
                Change(
                    kind=ChangeKind.ASSUMPTION_CHANGED,
                    subject=name,
                    before=str(old[name].value),
                    after=str(new[name].value),
                    explanation=f"basis {new[name].basis.value}",
                )
            )
    return changes


def _diff_facts(before: AnalysisBundle, after: AnalysisBundle) -> list[Change]:
    """A same-identity fact with a different amount is a restatement.

    Worth separating from every other reason a number moves: the company changed
    its own history, and nothing in the model did anything differently.
    """
    old: dict[str, Decimal] = {fact.fact_id: fact.value for fact in before.facts}
    labels = {fact.fact_id: f"{fact.metric_id} {fact.period.label}" for fact in before.facts}
    changes: list[Change] = []
    for fact in after.facts:
        previous = old.get(fact.fact_id)
        if previous is not None and previous != fact.value:
            changes.append(
                Change(
                    kind=ChangeKind.FACT_RESTATED,
                    subject=labels.get(fact.fact_id, fact.fact_id),
                    before=str(previous),
                    after=str(fact.value),
                    explanation="the filer restated this figure",
                )
            )
    return changes
