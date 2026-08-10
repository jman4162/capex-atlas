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

    scenario_values = 0
    for scenario in bundle.scenarios:
        scenario_values += len(scenario.values)
        findings.extend(_audit_scenario(bundle, scenario))

    findings.extend(_audit_reconciliation(bundle))
    findings.extend(_audit_graph(bundle))
    findings.extend(_audit_disclaimer(bundle))

    return AuditReport(
        findings=tuple(findings),
        values_checked=len(bundle.values) + scenario_values,
    )


def _audit_scenario(bundle: AnalysisBundle, scenario: object) -> list[AuditFinding]:
    """Scenario outputs are published figures and get walked like any other.

    They cite no filing, because a what-if rests on assumptions rather than
    evidence. What they must do instead is name the registry entries they drew
    on, so a reader can see which choices the answer depends on.
    """
    from capex_atlas.scenarios.model import ScenarioResult

    assert isinstance(scenario, ScenarioResult)
    problems: list[AuditFinding] = []
    name = scenario.definition.name

    for value in scenario.values:
        if value.formula_node_id is None or bundle.node(value.formula_node_id) is None:
            problems.append(
                AuditFinding(
                    severity=Severity.ERROR,
                    value_id=value.value_id,
                    label=f"{name}: {value.label}",
                    problem="scenario figure has no calculation node in the bundle",
                )
            )
        if value.status is not EvidenceStatus.SCENARIO and value.is_known:
            problems.append(
                AuditFinding(
                    severity=Severity.ERROR,
                    value_id=value.value_id,
                    label=f"{name}: {value.label}",
                    problem=(
                        f"a scenario output is marked {value.status.value}; "
                        "modelled figures are what-ifs"
                    ),
                )
            )

    if not scenario.definition.assumption_ids:
        problems.append(
            AuditFinding(
                severity=Severity.ERROR,
                value_id=scenario.definition.scenario_id,
                label=name,
                problem="names no registry assumptions, so its inputs cannot be traced",
            )
        )

    # Checking the tuple was non-empty made the requirement vacuous: a tuple
    # holding one empty string satisfied it, and the shipped example named
    # `useful_life.servers_and_network.googl`, which exists in no registry. An id
    # nobody can look up is not provenance.
    for assumption_id in scenario.definition.assumption_ids:
        if not assumption_id.strip():
            problems.append(
                AuditFinding(
                    severity=Severity.ERROR,
                    value_id=scenario.definition.scenario_id,
                    label=name,
                    problem="names a blank assumption id",
                )
            )
        elif bundle.assumption(assumption_id) is None:
            problems.append(
                AuditFinding(
                    severity=Severity.ERROR,
                    value_id=scenario.definition.scenario_id,
                    label=name,
                    problem=(f"cites assumption {assumption_id}, which the bundle does not carry"),
                )
            )
    return problems


def _audit_reconciliation(bundle: AnalysisBundle) -> list[AuditFinding]:
    """A bundle whose accounting identities failed is not publishable.

    The report was computed, embedded and then read by nobody: the pipeline
    published its results regardless, and the audit never looked. Corrupting
    ``Assets`` in the source produced fourteen failed balance-sheet identities, a
    published invested-capital figure a trillion dollars out, and a clean audit.

    The report is still built and still carried when a check fails, because being
    able to open a broken bundle and see what broke is how it gets diagnosed.
    What changes is that it can no longer pass.
    """
    report = bundle.validation
    if report is None:
        return [
            AuditFinding(
                severity=Severity.WARNING,
                value_id=bundle.entity_id,
                label=bundle.period_label,
                problem=("no reconciliation was run, so the figures rest on extraction alone"),
            )
        ]
    return [
        AuditFinding(
            severity=Severity.ERROR,
            value_id=bundle.entity_id,
            label=bundle.period_label,
            problem=f"accounting identity failed: {failure.detail}",
        )
        for failure in report.failures
    ]


def _disagreements(value: object, node: object) -> list[str]:
    """Ways a published value can contradict the calculation it points at.

    The audit used to ask only whether the node existed. That made it a
    reachability check over identifiers rather than a consistency check over
    content, and every one of these passed it: an amount edited by a dollar or by
    seventy billion, a unit changed from USD to percent, a period moved six years,
    a label swapped, and a value repointed at a different real node so that the
    figure and its stated derivation simply disagreed.

    It matters because ``verify`` -- which rebuilds from source and compares -- is
    the only other integrity check, and it needs the original inputs and refuses
    bundles it did not build. A reader who receives a bundle can run the audit and
    nothing else, so the audit has to be worth running.
    """
    from capex_atlas.schemas.calculation import CalculationNode
    from capex_atlas.schemas.values import AnalyticalValue

    assert isinstance(value, AnalyticalValue)
    assert isinstance(node, CalculationNode)
    problems: list[str] = []

    if value.value != node.result:
        problems.append(f"says {value.value} but its calculation node computed {node.result}")
    if value.unit != node.unit:
        problems.append(f"is in {value.unit} but its calculation produced {node.unit}")
    if value.status.rank < node.status.rank:
        # Only the overstating direction is an error. A caller may legitimately
        # weaken a status because it knows something the kernel did not see --
        # a vintage summary is marked scenario because the ramp behind it was
        # chosen, though the arithmetic on the cash flows is merely derived. The
        # reverse, claiming firmer evidence than the calculation produced, is the
        # move that lets an estimate be read as a reported fact.
        problems.append(
            f"claims to be {value.status.value}, which is firmer than the "
            f"{node.status.value} calculation behind it"
        )
    value_period = value.period.label if value.period else None
    if value_period != node.period_label:
        problems.append(f"covers {value_period} but its calculation covers {node.period_label}")

    # The id is a hash of what went into the node, so recomputing it detects a
    # node whose recorded inputs no longer explain the id it travels under.
    rederived = CalculationNode.derive_id(
        metric_id=node.metric_id,
        metric_version=node.metric_version,
        inputs=node.inputs + node.literal_inputs,
        assumption_ids=node.assumption_ids,
        period_label=node.period_label,
    )
    if rederived != node.node_id:
        problems.append(
            f"calculation node {node.node_id} does not hash to its own inputs; "
            "the recorded derivation cannot have produced this id"
        )
    return problems


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
    else:
        node = bundle.node(value.formula_node_id)
        if node is None:
            problems.append(
                error(f"calculation node {value.formula_node_id} is absent from the bundle")
            )
        else:
            problems.extend(error(problem) for problem in _disagreements(value, node))

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
