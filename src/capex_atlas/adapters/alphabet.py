"""Alphabet Inc. (GOOGL, CIK 1652044).

The first filer covered, chosen because the cloud segment reports both revenue
and operating income, capex guidance is given explicitly, and a disclosed change
in server useful lives makes the depreciation-lag effect visible in the filings
rather than only in theory.

Concept names below were read from Alphabet's own Company Facts payload; the
fixture under ``tests/fixtures`` pins the ones this adapter depends on.
"""

from __future__ import annotations

from capex_atlas.adapters.base import Availability, SegmentSupport
from capex_atlas.normalization.calendar import KNOWN_CALENDARS, FiscalCalendar
from capex_atlas.schemas.facts import Statement

ENTITY_ID = "GOOGL"
CIK = 1652044

STATEMENT_MAP: dict[str, Statement] = {
    "Assets": Statement.BALANCE_SHEET,
    "Liabilities": Statement.BALANCE_SHEET,
    "StockholdersEquity": Statement.BALANCE_SHEET,
    "PropertyPlantAndEquipmentNet": Statement.BALANCE_SHEET,
    "FinanceLeaseLiability": Statement.BALANCE_SHEET,
    "NetCashProvidedByUsedInOperatingActivities": Statement.CASH_FLOW,
    "PaymentsToAcquirePropertyPlantAndEquipment": Statement.CASH_FLOW,
    "RevenueFromContractWithCustomerExcludingAssessedTax": Statement.INCOME_STATEMENT,
    "OperatingIncomeLoss": Statement.INCOME_STATEMENT,
    "ResearchAndDevelopmentExpense": Statement.INCOME_STATEMENT,
    "NetIncomeLoss": Statement.INCOME_STATEMENT,
    "Depreciation": Statement.INCOME_STATEMENT,
    "RevenueRemainingPerformanceObligation": Statement.OPERATIONAL,
}

CAPEX_CONCEPTS = ("PaymentsToAcquirePropertyPlantAndEquipment",)
"""Cash purchases of property and equipment.

Finance-lease additions are capital deployment too, but they are not cash capex
and are not added in here. Combining them is a normalization choice the metrics
layer makes explicitly, under a name that says which definition is in use.
"""

REPORTED_SEGMENTS = ("Google Services", "Google Cloud", "Other Bets")


class AlphabetAdapter:
    entity_id = ENTITY_ID
    cik = CIK

    def calendar(self) -> FiscalCalendar:
        return KNOWN_CALENDARS[ENTITY_ID]

    def statement_map(self) -> dict[str, Statement]:
        return dict(STATEMENT_MAP)

    def capex_concepts(self) -> tuple[str, ...]:
        return CAPEX_CONCEPTS

    def segment_support(self, source: str) -> SegmentSupport:
        if source == "sec_companyfacts":
            return SegmentSupport(
                availability=Availability.NOT_IN_SOURCE,
                explanation=(
                    "Company Facts flattens away XBRL dimensions, so segment revenue and "
                    "operating income are absent from it. Alphabet does report them; "
                    "reaching them needs the filing's XBRL instance (the [xbrl] extra) "
                    "rather than this endpoint."
                ),
                known_segments=REPORTED_SEGMENTS,
            )
        return SegmentSupport(
            availability=Availability.AVAILABLE,
            explanation=f"{source} carries dimensional facts",
            known_segments=REPORTED_SEGMENTS,
        )


ADAPTERS: dict[str, AlphabetAdapter] = {ENTITY_ID: AlphabetAdapter()}
