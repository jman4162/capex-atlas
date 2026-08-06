"""Company Facts extraction, including the two traps that produce plausible-looking
wrong numbers: filing-level fiscal tags and duplicated comparatives."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from capex_atlas.normalization.calendar import FiscalCalendar
from capex_atlas.schemas.facts import Statement
from capex_atlas.schemas.source import SourceKind, SourceReference
from capex_atlas.xbrl.companyfacts import extract_facts

CALENDAR = FiscalCalendar(entity_id="EXMPL", fiscal_year_end_month=12)
SOURCE = SourceReference(kind=SourceKind.SEC_FILING, url="https://example.invalid/facts")
STATEMENTS = {
    "NetCashProvidedByUsedInOperatingActivities": Statement.CASH_FLOW,
    "PaymentsToAcquirePropertyPlantAndEquipment": Statement.CASH_FLOW,
    "Assets": Statement.BALANCE_SHEET,
}


def payload(concept: str, entries: list[dict[str, Any]], unit: str = "USD") -> dict[str, Any]:
    return {"facts": {"us-gaap": {concept: {"units": {unit: entries}}}}}


def run(document: dict[str, Any]):  # type: ignore[no-untyped-def]
    return extract_facts(
        document,
        entity_id="EXMPL",
        calendar=CALENDAR,
        source=SOURCE,
        statement_map=STATEMENTS,
    )


class TestFiscalTagTrap:
    def test_period_comes_from_dates_not_from_the_filing_tags(self):
        # Both entries were reported by the same fiscal-2026 annual filing, so
        # both carry fy 2026 / fp FY. Only one of them is a 2026 fact.
        document = payload(
            "Assets",
            [
                {"end": "2024-12-31", "val": 100, "fy": 2026, "fp": "FY", "filed": "2027-02-01"},
                {"end": "2026-12-31", "val": 300, "fy": 2026, "fp": "FY", "filed": "2027-02-01"},
            ],
        )
        result = run(document)
        by_label = {f.period.label: f.value for f in result.facts}
        assert by_label == {"2024@4": Decimal("100"), "2026@4": Decimal("300")}

    def test_comparatives_do_not_collapse_onto_one_year(self):
        document = payload(
            "Assets",
            [
                {"end": f"{year}-12-31", "val": year, "fy": 2026, "fp": "FY", "filed": "2027-02-01"}
                for year in (2022, 2023, 2024, 2025, 2026)
            ],
        )
        assert len(run(document).facts) == 5


class TestDuplicatesAndRestatements:
    def test_latest_filing_wins(self):
        document = payload(
            "NetCashProvidedByUsedInOperatingActivities",
            [
                {
                    "start": "2026-01-01",
                    "end": "2026-03-31",
                    "val": 100,
                    "filed": "2026-04-25",
                    "accn": "orig",
                },
                {
                    "start": "2026-01-01",
                    "end": "2026-03-31",
                    "val": 110,
                    "filed": "2027-02-01",
                    "accn": "restated",
                },
            ],
        )
        result = run(document)
        assert len(result.facts) == 1
        assert result.facts[0].value == Decimal("110")

    def test_a_changed_value_is_reported_as_a_restatement(self):
        document = payload(
            "NetCashProvidedByUsedInOperatingActivities",
            [
                {
                    "start": "2026-01-01",
                    "end": "2026-03-31",
                    "val": 100,
                    "filed": "2026-04-25",
                    "accn": "orig",
                },
                {
                    "start": "2026-01-01",
                    "end": "2026-03-31",
                    "val": 110,
                    "filed": "2027-02-01",
                    "accn": "restated",
                },
            ],
        )
        [restatement] = run(document).restatements
        assert restatement.superseded_value == Decimal("100")
        assert restatement.current_value == Decimal("110")
        assert restatement.difference == Decimal("10")
        assert restatement.superseded_accession == "orig"

    def test_repeating_the_same_value_is_not_a_restatement(self):
        document = payload(
            "NetCashProvidedByUsedInOperatingActivities",
            [
                {"start": "2026-01-01", "end": "2026-03-31", "val": 100, "filed": "2026-04-25"},
                {"start": "2026-01-01", "end": "2026-03-31", "val": 100, "filed": "2027-02-01"},
            ],
        )
        result = run(document)
        assert result.restatements == ()
        assert len(result.facts) == 1

    def test_an_earlier_filing_does_not_overwrite_a_later_one(self):
        document = payload(
            "NetCashProvidedByUsedInOperatingActivities",
            [
                {"start": "2026-01-01", "end": "2026-03-31", "val": 110, "filed": "2027-02-01"},
                {"start": "2026-01-01", "end": "2026-03-31", "val": 100, "filed": "2026-04-25"},
            ],
        )
        assert run(document).facts[0].value == Decimal("110")


class TestSelection:
    def test_unmapped_concepts_are_ignored(self):
        document = payload("SomeConceptNobodyClassified", [{"end": "2026-12-31", "val": 1}])
        assert run(document).facts == ()

    def test_odd_spans_are_skipped_with_a_reason(self):
        document = payload(
            "NetCashProvidedByUsedInOperatingActivities",
            [{"start": "2026-01-01", "end": "2026-08-31", "val": 1, "filed": "2026-09-01"}],
        )
        result = run(document)
        assert result.facts == ()
        assert "matches no standard period" in result.skipped[0].reason

    def test_units_are_kept_distinct(self):
        document = {
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "units": {
                            "USD": [{"end": "2026-12-31", "val": 300, "filed": "2027-02-01"}],
                            "EUR": [{"end": "2026-12-31", "val": 280, "filed": "2027-02-01"}],
                        }
                    }
                }
            }
        }
        assert {f.unit for f in run(document).facts} == {"USD", "EUR"}

    def test_facts_carry_a_checkable_citation(self):
        document = payload(
            "Assets",
            [
                {
                    "end": "2026-12-31",
                    "val": 300,
                    "filed": "2027-02-01",
                    "accn": "0001-26-1",
                    "form": "10-K",
                }
            ],
        )
        fact = run(document).facts[0]
        assert fact.source.accession == "0001-26-1"
        assert fact.source.form == "10-K"
        assert fact.source.is_verifiable
        assert fact.xbrl_concept == "Assets"
        assert fact.statement is Statement.BALANCE_SHEET

    def test_decimal_precision_survives_json_floats(self):
        document = payload(
            "Assets", [{"end": "2026-12-31", "val": 1234567890123, "filed": "2027-02-01"}]
        )
        assert run(document).facts[0].value == Decimal("1234567890123")
