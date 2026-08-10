from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from capex_atlas.bundle import (
    AnalysisBundle,
    BundleProvenance,
    ChangeKind,
    Severity,
    audit_bundle,
    canonical_json,
    content_only,
    diff_bundles,
    read_bundle,
    write_bundle,
)
from capex_atlas.schemas.calculation import CalculationNode
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.facts import FinancialFact, Statement
from capex_atlas.schemas.period import FiscalPeriod
from capex_atlas.schemas.source import SourceKind, SourceReference
from capex_atlas.schemas.values import AnalyticalValue

PERIOD = FiscalPeriod(fiscal_year=2026, fiscal_quarter=2)
SOURCE = SourceReference(
    kind=SourceKind.SEC_FILING, accession="0001-26-1", section="Statements of Cash Flows"
)


# A node id is a hash of the derivation, and the audit re-derives it, so a
# hand-written "calc:1" is a node that cannot have produced its own id.
NODE_ID = CalculationNode.derive_id(
    metric_id="fcf.reported",
    metric_version="1.0.0",
    inputs=(),
    assumption_ids=(),
    period_label=PERIOD.label,
)


def node(node_id: str = NODE_ID, **overrides: object) -> CalculationNode:
    fields: dict[str, object] = {
        "node_id": node_id,
        "metric_id": "fcf.reported",
        "metric_version": "1.0.0",
        "formula": "cfo - capex",
        "inputs": (),
        "result": Decimal("60"),
        "unit": "USD",
        "status": EvidenceStatus.DERIVED,
        "period_label": PERIOD.label,
    }
    fields.update(overrides)
    return CalculationNode(**fields)  # type: ignore[arg-type]


def value(**overrides: object) -> AnalyticalValue:
    fields: dict[str, object] = {
        "value_id": NODE_ID,
        "value": Decimal("60"),
        "unit": "USD",
        "status": EvidenceStatus.DERIVED,
        "period": PERIOD,
        "label": "free cash flow",
        "formula_node_id": NODE_ID,
        "source_ids": (SOURCE.source_id,),
    }
    fields.update(overrides)
    return AnalyticalValue(**fields)  # type: ignore[arg-type]


def bundle(**overrides: object) -> AnalysisBundle:
    fields: dict[str, object] = {
        "entity_id": "GOOGL",
        "period_label": PERIOD.label,
        "extra_sources": (SOURCE,),
        "values": (value(),),
        "calculations": (node(),),
        "provenance": BundleProvenance(
            created_at=datetime(2026, 8, 6, tzinfo=UTC), package_version="0.1.0"
        ),
    }
    fields.update(overrides)
    return AnalysisBundle(**fields)  # type: ignore[arg-type]


class TestAuditCatchesUnsupportedNumbers:
    """The audit is only worth having if it fails when it should."""

    def test_a_well_formed_bundle_passes(self):
        report = audit_bundle(bundle())
        assert report.passed
        assert report.values_checked == 1

    def test_a_value_with_no_calculation_node_fails(self):
        report = audit_bundle(bundle(values=(value(formula_node_id=None),)))
        assert not report.passed
        assert "no calculation node" in report.errors[0].problem

    def test_a_value_whose_node_is_missing_fails(self):
        report = audit_bundle(bundle(values=(value(formula_node_id="calc:absent"),)))
        assert not report.passed
        assert "absent from the bundle" in report.errors[0].problem

    def test_a_value_with_no_evidence_at_all_fails(self):
        report = audit_bundle(bundle(values=(value(source_ids=(), assumption_ids=()),)))
        assert not report.passed
        assert "nothing supports this number" in report.errors[0].problem

    def test_citing_a_source_the_bundle_does_not_carry_fails(self):
        report = audit_bundle(bundle(values=(value(source_ids=("src:ghost",)),)))
        assert not report.passed
        assert "does not carry" in report.errors[0].problem

    def test_using_an_assumption_the_bundle_does_not_carry_fails(self):
        report = audit_bundle(bundle(values=(value(assumption_ids=("tax.missing",)),)))
        assert not report.passed

    def test_an_unresolved_value_needs_no_supporting_chain(self):
        # Saying a figure is unknown is honest and requires no evidence, only a
        # node recording what was attempted.
        unknown = value(value=None, status=EvidenceStatus.UNRESOLVED, source_ids=())
        attempted = node(result=None, status=EvidenceStatus.UNRESOLVED)
        assert audit_bundle(bundle(values=(unknown,), calculations=(attempted,))).passed

    def test_a_computed_value_claiming_reported_status_fails(self):
        # Was a warning while nothing compared a value with its node. Overstating
        # the evidence behind a figure is the direction that misleads a reader,
        # so it is now an error.
        report = audit_bundle(bundle(values=(value(status=EvidenceStatus.REPORTED),)))
        assert not report.passed
        assert any("firmer than the" in error.problem for error in report.errors)

    def test_a_value_without_a_period_warns(self):
        report = audit_bundle(bundle(values=(value(period=None),)))
        assert any("cannot be compared" in w.problem for w in report.warnings)

    def test_a_bundle_without_a_disclaimer_fails(self):
        report = audit_bundle(bundle(disclaimer="  "))
        assert not report.passed
        assert any(f.severity is Severity.ERROR for f in report.findings)

    def test_findings_read_clearly(self):
        report = audit_bundle(bundle(values=(value(formula_node_id=None),)))
        assert str(report.errors[0]).startswith("[error] free cash flow:")


class TestDeterminism:
    def test_two_bundles_with_the_same_content_serialize_identically(self):
        assert content_only(bundle()) == content_only(bundle())

    def test_provenance_is_the_only_volatile_part(self):
        later = bundle(
            provenance=BundleProvenance(
                created_at=datetime(2027, 1, 1, tzinfo=UTC), package_version="9.9.9"
            )
        )
        assert canonical_json(bundle()) != canonical_json(later)
        assert content_only(bundle()) == content_only(later)

    def test_serialization_sorts_keys(self):
        payload = json.loads(canonical_json(bundle()))
        assert list(payload) == sorted(payload)


class TestRoundTrip:
    def test_write_then_read_preserves_content(self, tmp_path: Path):
        original = bundle()
        path = write_bundle(original, tmp_path)
        assert content_only(read_bundle(path)) == content_only(original)

    def test_reading_from_the_directory_works_too(self, tmp_path: Path):
        write_bundle(bundle(), tmp_path)
        assert read_bundle(tmp_path).entity_id == "GOOGL"

    def test_the_disclaimer_is_written_alongside(self, tmp_path: Path):
        write_bundle(bundle(), tmp_path)
        text = (tmp_path / "DISCLAIMER.md").read_text()
        assert "not investment" in text.lower() or "professional advice" in text.lower()

    def test_sources_are_exported_separately(self, tmp_path: Path):
        write_bundle(bundle(), tmp_path)
        exported = json.loads((tmp_path / "sources.json").read_text())
        assert exported[0]["accession"] == "0001-26-1"

    def test_sources_are_derived_from_facts_rather_than_stored_twice(self, tmp_path: Path):
        # Storing them beside the facts made a third of a real bundle redundant
        # bytes, and let the two lists disagree.
        fact = FinancialFact(
            entity_id="GOOGL",
            metric_id="Assets",
            value=Decimal("1"),
            unit="USD",
            period=PERIOD,
            statement=Statement.BALANCE_SHEET,
            source=SOURCE,
        )
        derived = AnalysisBundle(entity_id="GOOGL", period_label=PERIOD.label, facts=(fact,))
        assert [s.source_id for s in derived.sources] == [SOURCE.source_id]
        assert "sources" not in json.loads(canonical_json(derived))

    def test_parquet_sidecars_appear_when_there_are_rows(self, tmp_path: Path):
        fact = FinancialFact(
            entity_id="GOOGL",
            metric_id="Assets",
            value=Decimal("1"),
            unit="USD",
            period=PERIOD,
            statement=Statement.BALANCE_SHEET,
            source=SOURCE,
        )
        write_bundle(bundle(facts=(fact,)), tmp_path)
        assert (tmp_path / "facts.parquet").exists()
        assert not (tmp_path / "claims.parquet").exists()


class TestDiff:
    def test_identical_bundles_show_no_changes(self):
        assert diff_bundles(bundle(), bundle()).identical

    def test_a_changed_value_is_reported(self):
        after = bundle(values=(value(value=Decimal("70")),))
        [change] = diff_bundles(bundle(), after).of_kind(ChangeKind.VALUE_CHANGED)
        assert change.before == "60"
        assert change.after == "70"

    def test_a_metric_version_bump_is_named_as_the_cause(self):
        after = bundle(
            values=(value(value=Decimal("70"), formula_node_id="calc:2"),),
            calculations=(node("calc:2", metric_version="2.0.0", result=Decimal("70")),),
        )
        [change] = diff_bundles(bundle(), after).of_kind(ChangeKind.VALUE_CHANGED)
        assert "metric version 1.0.0 -> 2.0.0" in change.explanation

    def test_a_restated_fact_is_distinguished_from_a_model_change(self):
        # The company changed its own history; nothing in the model moved.
        original = FinancialFact(
            entity_id="GOOGL",
            metric_id="Assets",
            value=Decimal("100"),
            unit="USD",
            period=PERIOD,
            statement=Statement.BALANCE_SHEET,
            source=SOURCE,
        )
        restated = original.model_copy(update={"value": Decimal("110")})
        result = diff_bundles(bundle(facts=(original,)), bundle(facts=(restated,)))
        [change] = result.of_kind(ChangeKind.FACT_RESTATED)
        assert change.before == "100"
        assert "restated" in change.explanation

    def test_added_and_removed_values_are_reported(self):
        extra = value(value_id="calc:2", label="capex intensity", formula_node_id="calc:1")
        forward = diff_bundles(bundle(), bundle(values=(value(), extra)))
        assert forward.of_kind(ChangeKind.ADDED)
        backward = diff_bundles(bundle(values=(value(), extra)), bundle())
        assert backward.of_kind(ChangeKind.REMOVED)

    def test_a_status_change_is_reported_on_its_own(self):
        after = bundle(values=(value(status=EvidenceStatus.ESTIMATED),))
        [change] = diff_bundles(bundle(), after).of_kind(ChangeKind.STATUS_CHANGED)
        assert change.before == "derived"
        assert change.after == "estimated"


class TestCitationIdentity:
    def test_narrowing_a_citation_derives_a_new_id(self):
        # model_copy would keep the old id, which once made every fact in a
        # bundle appear to come from the same filing.
        narrowed = SOURCE.narrow(accession="0002-26-9")
        assert narrowed.source_id != SOURCE.source_id
        assert narrowed.accession == "0002-26-9"

    def test_narrowing_to_the_same_fields_is_stable(self):
        assert SOURCE.narrow().source_id == SOURCE.source_id

    def test_model_copy_keeps_the_stale_id(self):
        # Documented so the trap stays visible: this is why narrow() exists.
        stale = SOURCE.model_copy(update={"accession": "0002-26-9"})
        assert stale.source_id == SOURCE.source_id


def test_unsupported_entity_names_the_covered_filers():
    from capex_atlas.bundle import UnsupportedEntityError, build_analysis

    with pytest.raises(UnsupportedEntityError, match="out of scope"):
        build_analysis({}, entity_id="AMZN", period_label="2025FY", source=SOURCE)


class TestAuditDetectsTampering:
    """Every mutation here passed the audit before it compared content.

    The audit walked identifiers and asked whether they resolved. It never asked
    whether what they resolved to agreed with the figure citing it, so a
    published number could be edited freely as long as it still pointed at some
    real node. `verify` catches this by rebuilding from source, but it needs the
    original inputs and refuses bundles it did not build, so a reader who
    receives a bundle has the audit and nothing else.
    """

    @staticmethod
    def tampered(**edits: object) -> bool:
        """Whether the audit passes a bundle with one value edited."""
        return audit_bundle(bundle(values=(value(**edits),))).passed

    def test_an_edited_amount_is_caught(self):
        assert not self.tampered(value=Decimal("60.01"))
        assert not self.tampered(value=Decimal("1"))
        assert not self.tampered(value=None)

    def test_an_edited_unit_is_caught(self):
        assert not self.tampered(unit="EUR")
        assert not self.tampered(unit="percent")

    def test_an_edited_period_is_caught(self):
        assert not self.tampered(period=FiscalPeriod.parse("2019FY"))

    def test_overstating_the_evidence_is_caught(self):
        assert not self.tampered(status=EvidenceStatus.REPORTED)

    def test_pointing_at_a_different_real_node_is_caught(self):
        # The subtle one: nothing is missing, the citation resolves, and the
        # figure still contradicts the calculation it names.
        other = node(node_id="calc:other", result=Decimal("71"))
        report = audit_bundle(
            bundle(
                values=(value(formula_node_id="calc:other"),),
                calculations=(node(), other),
            )
        )
        assert not report.passed
        assert any("computed" in error.problem for error in report.errors)

    def test_a_node_that_does_not_hash_to_its_inputs_is_caught(self):
        forged = node(node_id="calc:handwritten")
        report = audit_bundle(
            bundle(values=(value(formula_node_id="calc:handwritten"),), calculations=(forged,))
        )
        assert not report.passed
        assert any("does not hash" in error.problem for error in report.errors)

    def test_weakening_a_status_is_allowed(self):
        # A caller may know the figure rests on something the kernel did not see.
        # A vintage summary is a scenario though its arithmetic is only derived.
        assert self.tampered(status=EvidenceStatus.ESTIMATED)
