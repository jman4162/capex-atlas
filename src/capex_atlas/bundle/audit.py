"""Auditing a bundle.

This is the acceptance test for the whole package. Walk every published value and
fail if any of them lacks a calculation node, a source, or a registry-backed
assumption. If a number can reach a reader without that chain intact, none of the
architecture above it was worth building.

The audit reports rather than raises, so a caller can show a reader exactly which
figures are unsupported instead of only that something is.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from capex_atlas.bundle.model import AnalysisBundle
from capex_atlas.schemas.evidence import EvidenceStatus


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class AuditFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: Severity
    value_id: str
    label: str | None
    problem: str

    def __str__(self) -> str:
        name = self.label or self.value_id
        return f"[{self.severity.value}] {name}: {self.problem}"


class AuditReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    findings: tuple[AuditFinding, ...]
    values_checked: int

    @property
    def passed(self) -> bool:
        return not any(f.severity is Severity.ERROR for f in self.findings)

    @property
    def errors(self) -> tuple[AuditFinding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[AuditFinding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)


def audit_bundle(bundle: AnalysisBundle) -> AuditReport:
    """Check that every published value can be traced back to evidence."""
    findings: list[AuditFinding] = []

    for value in bundle.values:
        findings.extend(_audit_value(bundle, value))

    findings.extend(_audit_graph(bundle))
    findings.extend(_audit_disclaimer(bundle))

    return AuditReport(findings=tuple(findings), values_checked=len(bundle.values))


def _audit_value(bundle: AnalysisBundle, value: object) -> list[AuditFinding]:
    from capex_atlas.schemas.values import AnalyticalValue

    assert isinstance(value, AnalyticalValue)
    problems: list[AuditFinding] = []

    def error(problem: str) -> AuditFinding:
        return AuditFinding(
            severity=Severity.ERROR, value_id=value.value_id, label=value.label, problem=problem
        )

    def warn(problem: str) -> AuditFinding:
        return AuditFinding(
            severity=Severity.WARNING, value_id=value.value_id, label=value.label, problem=problem
        )

    # An unresolved value is an honest statement that something is unknown, and
    # it needs no supporting chain, only a node explaining what was attempted.
    unresolved = value.status is EvidenceStatus.UNRESOLVED

    if value.formula_node_id is None:
        problems.append(error("no calculation node; the formula behind it is unrecorded"))
    elif bundle.node(value.formula_node_id) is None:
        problems.append(
            error(f"calculation node {value.formula_node_id} is absent from the bundle")
        )

    if not unresolved and not value.source_ids and not value.assumption_ids:
        problems.append(error("neither a source nor an assumption; nothing supports this number"))

    for source_id in value.source_ids:
        if bundle.source(source_id) is None:
            problems.append(error(f"cites source {source_id}, which the bundle does not carry"))

    for assumption_id in value.assumption_ids:
        assumption = bundle.assumption(assumption_id)
        if assumption is None:
            problems.append(
                error(f"uses assumption {assumption_id}, which the bundle does not carry")
            )
        elif assumption.citation is None and assumption.basis.value not in (
            "user_input",
            "derived_from_facts",
        ):
            problems.append(error(f"assumption {assumption_id} claims a basis but cites nothing"))

    if value.status is EvidenceStatus.REPORTED and value.formula_node_id is not None:
        problems.append(
            warn("marked reported but produced by a calculation; a computed value is derived")
        )

    if value.period is None and not unresolved:
        problems.append(warn("no period; a figure without a period cannot be compared"))

    return problems


def _audit_graph(bundle: AnalysisBundle) -> list[AuditFinding]:
    """Every input a node names must itself be present or be a leaf."""
    findings: list[AuditFinding] = []
    node_ids = {node.node_id for node in bundle.calculations}
    fact_value_ids = {value.value_id for value in bundle.values}

    for node in bundle.calculations:
        for input_id in node.inputs:
            known = (
                input_id in node_ids
                or input_id in fact_value_ids
                or input_id.startswith(("val:", "fact:"))
            )
            if not known:
                findings.append(
                    AuditFinding(
                        severity=Severity.WARNING,
                        value_id=node.node_id,
                        label=node.metric_id,
                        problem=f"input {input_id} is neither a node nor a recognizable leaf",
                    )
                )
    return findings


def _audit_disclaimer(bundle: AnalysisBundle) -> list[AuditFinding]:
    if bundle.disclaimer.strip():
        return []
    return [
        AuditFinding(
            severity=Severity.ERROR,
            value_id="<bundle>",
            label=None,
            problem="no disclaimer; a bundle travels and must carry its conditions",
        )
    ]
