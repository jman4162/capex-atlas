from __future__ import annotations

from decimal import Decimal

import pytest

from capex_atlas.schemas import FinancialFact, FiscalPeriod, PeriodKind, SourceKind, SourceReference
from capex_atlas.schemas.hashing import canonical, stable_id
from capex_atlas.schemas.values import AnalyticalValue


class TestHashing:
    def test_is_deterministic(self):
        assert stable_id("x", "a", 1) == stable_id("x", "a", 1)

    def test_distinguishes_field_boundaries(self):
        # "ab" + "c" must not collide with "a" + "bc".
        assert stable_id("x", "ab", "c") != stable_id("x", "a", "bc")

    def test_mapping_order_does_not_matter(self):
        assert canonical({"a": 1, "b": 2}) == canonical({"b": 2, "a": 1})

    def test_decimal_scale_does_not_matter(self):
        assert canonical(Decimal("1.50")) == canonical(Decimal("1.5"))


class TestFiscalPeriod:
    @pytest.mark.parametrize("label", ["2026Q2", "2026FY", "2026YTD3", "2026TTM2", "2026@4"])
    def test_label_round_trip(self, label: str):
        assert FiscalPeriod.parse(label).label == label

    def test_rejects_unparseable_labels(self):
        with pytest.raises(ValueError, match="unrecognized period"):
            FiscalPeriod.parse("Q2-2026")

    def test_rejects_quarter_out_of_range(self):
        with pytest.raises(ValueError, match="fiscal_quarter out of range"):
            FiscalPeriod(fiscal_year=2026, fiscal_quarter=5)

    def test_fiscal_year_needs_no_quarter(self):
        assert FiscalPeriod(fiscal_year=2026, kind=PeriodKind.FISCAL_YEAR).label == "2026FY"

    def test_quarter_requires_a_quarter_number(self):
        with pytest.raises(ValueError, match="requires a fiscal_quarter"):
            FiscalPeriod(fiscal_year=2026)

    def test_rejects_inverted_dates(self):
        from datetime import date

        with pytest.raises(ValueError, match="starts after it ends"):
            FiscalPeriod(
                fiscal_year=2026,
                fiscal_quarter=2,
                start=date(2026, 6, 30),
                end=date(2026, 4, 1),
            )


class TestSourceReference:
    def test_id_is_derived_when_absent(self, source: SourceReference):
        assert source.source_id.startswith("src:")

    def test_identical_citations_share_an_id(self):
        first = SourceReference(kind=SourceKind.SEC_FILING, accession="1", section="Note 1")
        second = SourceReference(kind=SourceKind.SEC_FILING, accession="1", section="Note 1")
        assert first.source_id == second.source_id

    def test_different_passages_get_different_ids(self):
        first = SourceReference(kind=SourceKind.SEC_FILING, accession="1", section="Note 1")
        second = SourceReference(kind=SourceKind.SEC_FILING, accession="1", section="Note 2")
        assert first.source_id != second.source_id

    def test_accession_alone_is_not_verifiable(self):
        bare = SourceReference(kind=SourceKind.SEC_FILING, accession="1")
        assert not bare.is_verifiable


class TestFinancialFact:
    def test_is_immutable(self, fact: FinancialFact):
        with pytest.raises(Exception, match=r"frozen|immutable"):
            fact.value = Decimal("2")  # type: ignore[misc]

    def test_id_is_derived_from_identity_not_value(self, fact: FinancialFact):
        restated = fact.model_copy(update={"value": Decimal("999")})
        # Same company, concept, period and unit: a restatement of the same fact,
        # which the reconciliation layer needs to be able to notice.
        assert restated.fact_id == fact.fact_id

    def test_dimensions_change_the_id(self, fact: FinancialFact):
        segmented = fact.model_copy(update={"dimensions": {"segment": "Cloud"}})
        assert segmented.model_dump()["fact_id"] == fact.fact_id  # copy keeps the old id
        rebuilt = FinancialFact(
            **fact.model_dump(exclude={"fact_id"}) | {"dimensions": {"segment": "Cloud"}}
        )
        assert rebuilt.fact_id != fact.fact_id

    def test_json_round_trip_preserves_decimal_exactly(self, fact: FinancialFact):
        precise = fact.model_copy(update={"value": Decimal("1234.5678901234567890")})
        restored = FinancialFact.model_validate_json(precise.model_dump_json())
        assert restored.value == Decimal("1234.5678901234567890")

    def test_json_round_trip_is_lossless(self, fact: FinancialFact):
        assert FinancialFact.model_validate_json(fact.model_dump_json()) == fact


class TestAnalyticalValue:
    def test_from_fact_carries_source_and_status(self, fact: FinancialFact):
        value = AnalyticalValue.from_fact(fact)
        assert value.value == fact.value
        assert value.status is fact.status
        assert value.source_ids == (fact.source.source_id,)
        assert value.period == fact.period

    def test_same_fact_lifts_to_the_same_id(self, fact: FinancialFact):
        assert AnalyticalValue.from_fact(fact).value_id == AnalyticalValue.from_fact(fact).value_id

    def test_contradictory_amounts_are_distinct_calculation_inputs(self, fact: FinancialFact):
        # fact_id is identity-only so restatements are detectable, but two
        # different amounts must never collide as inputs to the same graph.
        restated = fact.model_copy(update={"value": Decimal("999")})
        assert restated.fact_id == fact.fact_id
        original_id = AnalyticalValue.from_fact(fact).value_id
        assert AnalyticalValue.from_fact(restated).value_id != original_id

    def test_str_shows_the_status_glyph(self, fact: FinancialFact):
        assert str(AnalyticalValue.from_fact(fact)).startswith("●")

    def test_unknown_value_renders_as_a_dash(self):
        from capex_atlas.schemas.evidence import EvidenceStatus

        unknown = AnalyticalValue(
            value_id="v", value=None, unit="USD", status=EvidenceStatus.UNRESOLVED
        )
        assert "—" in str(unknown)
        assert not unknown.is_known
