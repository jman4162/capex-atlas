"""Microsoft Corporation (MSFT, CIK 789019).

The filer that proves the fiscal calendar works. Microsoft's year ends 30 June,
so its 2026Q2 covers October to December 2025 while Alphabet's covers April to
June 2026. Any comparison that treats the labels as equivalent is wrong before
the arithmetic starts, and until this adapter existed that path was only
exercised by synthetic unit tests.

Two tag differences from Alphabet, both found by reading Microsoft's own Company
Facts rather than assumed: marketable securities are tagged
``ShortTermInvestments``, and the current revenue tag is
``RevenueFromContractWithCustomerExcludingAssessedTax`` -- the reverse of
Alphabet's ordering, which is why alias order is per-filer.
"""

from __future__ import annotations

from capex_atlas.adapters.base import Availability, SegmentSupport
from capex_atlas.normalization.calendar import KNOWN_CALENDARS, FiscalCalendar
from capex_atlas.schemas.facts import Statement

ENTITY_ID = "MSFT"
CIK = 789019

STATEMENT_MAP: dict[str, Statement] = {
    "Assets": Statement.BALANCE_SHEET,
    "AssetsCurrent": Statement.BALANCE_SHEET,
    "Liabilities": Statement.BALANCE_SHEET,
    "LiabilitiesCurrent": Statement.BALANCE_SHEET,
    "StockholdersEquity": Statement.BALANCE_SHEET,
    "PropertyPlantAndEquipmentNet": Statement.BALANCE_SHEET,
    "CashAndCashEquivalentsAtCarryingValue": Statement.BALANCE_SHEET,
    "ShortTermInvestments": Statement.BALANCE_SHEET,
    "NetCashProvidedByUsedInOperatingActivities": Statement.CASH_FLOW,
    "PaymentsToAcquirePropertyPlantAndEquipment": Statement.CASH_FLOW,
    "FinanceLeasePrincipalPayments": Statement.CASH_FLOW,
    "RevenueFromContractWithCustomerExcludingAssessedTax": Statement.INCOME_STATEMENT,
    "Revenues": Statement.INCOME_STATEMENT,
    "OperatingIncomeLoss": Statement.INCOME_STATEMENT,
    "ResearchAndDevelopmentExpense": Statement.INCOME_STATEMENT,
    "NetIncomeLoss": Statement.INCOME_STATEMENT,
    "IncomeTaxExpenseBenefit": Statement.INCOME_STATEMENT,
    "Depreciation": Statement.INCOME_STATEMENT,
    "RevenueRemainingPerformanceObligation": Statement.OPERATIONAL,
}

CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    # Current tag first. Microsoft moved to the contract-revenue tag and left
    # `Revenues` behind years ago; Alphabet went the other way.
    "revenue.total": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
    ),
    "cash_flow.operating": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex.cash": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    # Microsoft does not tag proceeds from equipment disposals, so the
    # standardized free-cash-flow definition resolves to unknown for this filer
    # rather than quietly treating the gap as zero.
    "capex.disposal_proceeds": (),
    "capex.finance_lease_principal": ("FinanceLeasePrincipalPayments",),
    "depreciation": ("Depreciation",),
    "income.operating": ("OperatingIncomeLoss",),
    "balance.assets": ("Assets",),
    "balance.current_liabilities": ("LiabilitiesCurrent",),
    "balance.cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "balance.marketable_securities": ("ShortTermInvestments",),
}

CUMULATIVE_CONCEPTS: tuple[str, ...] = ("capex.cash", "cash_flow.operating")

CAPEX_CONCEPTS = ("PaymentsToAcquirePropertyPlantAndEquipment",)

REPORTED_SEGMENTS = (
    "Productivity and Business Processes",
    "Intelligent Cloud",
    "More Personal Computing",
)


class MicrosoftAdapter:
    entity_id = ENTITY_ID
    cik = CIK

    def calendar(self) -> FiscalCalendar:
        return KNOWN_CALENDARS[ENTITY_ID]

    def statement_map(self) -> dict[str, Statement]:
        return dict(STATEMENT_MAP)

    def capex_concepts(self) -> tuple[str, ...]:
        return CAPEX_CONCEPTS

    def concept_aliases(self) -> dict[str, tuple[str, ...]]:
        return dict(CONCEPT_ALIASES)

    def cumulative_concepts(self) -> tuple[str, ...]:
        return CUMULATIVE_CONCEPTS

    def segment_support(self, source: str) -> SegmentSupport:
        if source == "sec_companyfacts":
            return SegmentSupport(
                availability=Availability.NOT_IN_SOURCE,
                explanation=(
                    "Company Facts flattens away XBRL dimensions. Microsoft reports "
                    "Intelligent Cloud revenue and operating income but never breaks out "
                    "Azure revenue in dollars, so even the filing's own XBRL cannot supply "
                    "an Azure margin."
                ),
                known_segments=REPORTED_SEGMENTS,
            )
        return SegmentSupport(
            availability=Availability.AVAILABLE,
            explanation=f"{source} carries dimensional facts",
            known_segments=REPORTED_SEGMENTS,
        )
