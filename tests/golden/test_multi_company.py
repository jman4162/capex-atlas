"""Three filers through the same pipeline, offline against pinned fixtures.

The point of covering more than one company is not breadth for its own sake. It
is that a second and third filer test things a single one cannot: whether the
fiscal calendar actually works, whether the adapter seam holds, and whether the
package's own comparability warnings are true.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from capex_atlas.adapters import ADAPTERS, adapter_for
from capex_atlas.bundle import audit_bundle, build_analysis
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.source import SourceKind, SourceReference

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Each filer at its own most recent full year. Microsoft's fiscal 2026 closed in
# June 2026; Alphabet's and Meta's 2025 closed that December.
FILERS = {"GOOGL": "2025FY", "MSFT": "2026FY", "META": "2025FY"}


def load(ticker: str):  # type: ignore[no-untyped-def]
    path = FIXTURES / f"{ticker.lower()}_companyfacts_trimmed.json"
    body = path.read_text()
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    expected = manifest[path.name]["sha256"]
    assert hashlib.sha256(body.encode()).hexdigest() == expected, (
        f"{path.name} changed; re-pin it deliberately with scripts/build_fixture.py"
    )
    return json.loads(body)


@pytest.fixture(scope="module")
def bundles():  # type: ignore[no-untyped-def]
    built = {}
    for ticker, period in FILERS.items():
        built[ticker] = build_analysis(
            load(ticker),
            entity_id=ticker,
            period_label=period,
            source=SourceReference(kind=SourceKind.SEC_FILING, url="https://data.sec.gov/x"),
        )
    return built


class TestEveryFilerWorks:
    @pytest.mark.parametrize("ticker", list(FILERS))
    def test_the_bundle_audits_clean(self, ticker: str, bundles):  # type: ignore[no-untyped-def]
        report = audit_bundle(bundles[ticker])
        assert report.passed, [str(f) for f in report.errors]

    @pytest.mark.parametrize("ticker", list(FILERS))
    def test_the_accounting_identities_hold(self, ticker: str, bundles):  # type: ignore[no-untyped-def]
        validation = bundles[ticker].validation
        assert validation is not None
        assert validation.passed, [f.detail for f in validation.failures]
        assert validation.verified_count > 20

    @pytest.mark.parametrize("ticker", list(FILERS))
    def test_free_cash_flow_is_computed(self, ticker: str, bundles):  # type: ignore[no-untyped-def]
        value = bundles[ticker].value("free cash flow (reported basis)")
        assert value is not None and value.is_known
        assert value.status is EvidenceStatus.DERIVED


class TestTheFiscalCalendarActuallyWorks:
    """Until Microsoft, this path was only exercised by synthetic unit tests."""

    def test_microsofts_year_ends_in_june(self, bundles):  # type: ignore[no-untyped-def]
        capex = [
            fact
            for fact in bundles["MSFT"].facts
            if fact.period.label == "2026FY" and fact.period.end is not None
        ]
        assert capex
        assert capex[0].period.end.month == 6

    def test_alphabets_year_ends_in_december(self, bundles):  # type: ignore[no-untyped-def]
        annual = [
            fact
            for fact in bundles["GOOGL"].facts
            if fact.period.label == "2025FY" and fact.period.end is not None
        ]
        assert annual
        assert annual[0].period.end.month == 12

    def test_the_same_label_covers_different_months(self, bundles):  # type: ignore[no-untyped-def]
        # The reason the package models fiscal periods per filer at all.
        msft = next(f for f in bundles["MSFT"].facts if f.period.label == "2026FY" and f.period.end)
        googl = next(
            f for f in bundles["GOOGL"].facts if f.period.label == "2025FY" and f.period.end
        )
        assert msft.period.end != googl.period.end


class TestTheAdapterSeamHolds:
    def test_each_filer_resolves_revenue_despite_different_tag_orders(self, bundles):  # type: ignore[no-untyped-def]
        # Alphabet's current tag is `Revenues`; Microsoft's and Meta's is the
        # contract-revenue tag. Alias order is per-filer for this reason.
        for ticker in FILERS:
            intensity = bundles[ticker].value("capex intensity")
            assert intensity is not None and intensity.is_known, ticker

    def test_microsoft_reports_no_disposal_proceeds_so_the_metric_is_unknown(self, bundles):  # type: ignore[no-untyped-def]
        value = bundles["MSFT"].value("free cash flow (standardized)")
        assert value is not None
        assert value.status is EvidenceStatus.UNRESOLVED

    def test_no_adapter_names_a_concept_the_analysis_does_not_ask_for(self):
        from capex_atlas.adapters.base import REQUIRED_SERIES

        for ticker, adapter in ADAPTERS.items():
            declared = set(adapter.concept_aliases())
            missing = set(REQUIRED_SERIES) - declared
            assert not missing, f"{ticker} does not alias {sorted(missing)}"

    def test_an_uncovered_filer_is_refused_by_name(self):
        from capex_atlas.adapters import UnsupportedEntityError

        with pytest.raises(UnsupportedEntityError, match="out of scope"):
            adapter_for("AMZN")


class TestComparabilityWarningsAreTrue:
    """The README says headline capex is not comparable. Check that it is not."""

    def test_capex_intensity_differs_widely_across_the_three(self, bundles):  # type: ignore[no-untyped-def]
        intensities = {ticker: bundles[ticker].value("capex intensity").value for ticker in FILERS}
        assert all(v is not None for v in intensities.values())
        spread = max(intensities.values()) - min(intensities.values())
        assert spread > Decimal("0.05"), intensities

    def test_meta_has_no_segment_to_divide_infrastructure_into(self):
        support = adapter_for("META").segment_support("sec_companyfacts")
        assert support.availability.value == "not_disclosed"
        assert "not the same measure" in support.explanation

    def test_microsoft_never_breaks_out_azure_in_dollars(self):
        support = adapter_for("MSFT").segment_support("sec_companyfacts")
        assert "Azure" in support.explanation
