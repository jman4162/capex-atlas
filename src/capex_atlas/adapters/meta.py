"""Meta Platforms, Inc. (META, CIK 1326801).

The filer that breaks naive cross-company capex comparison. Alphabet and
Microsoft sell cloud capacity, so their infrastructure spending has directly
attributable revenue. Meta's does not: the servers support advertising and
engagement, and there is no line item that says what they earned. Capex
intensity is computable for all three; only for two of them does it mean
something close to the same thing.

Meta also carries the clearest useful-life change in the group. It extended most
servers and network assets to 5.5 years effective January 2025 and quantified
the effect, which is the depreciation-lag lesson with the company's own numbers
attached. See the cited registry entries.
"""

from __future__ import annotations

from capex_atlas.adapters.base import Availability, SegmentSupport
from capex_atlas.normalization.calendar import KNOWN_CALENDARS, FiscalCalendar
from capex_atlas.schemas.facts import Statement

ENTITY_ID = "META"
CIK = 1326801

STATEMENT_MAP: dict[str, Statement] = {
    "Assets": Statement.BALANCE_SHEET,
    "AssetsCurrent": Statement.BALANCE_SHEET,
    "Liabilities": Statement.BALANCE_SHEET,
    "LiabilitiesCurrent": Statement.BALANCE_SHEET,
    "StockholdersEquity": Statement.BALANCE_SHEET,
    "PropertyPlantAndEquipmentNet": Statement.BALANCE_SHEET,
    "FinanceLeaseLiability": Statement.BALANCE_SHEET,
    "CashAndCashEquivalentsAtCarryingValue": Statement.BALANCE_SHEET,
    "MarketableSecuritiesCurrent": Statement.BALANCE_SHEET,
    "NetCashProvidedByUsedInOperatingActivities": Statement.CASH_FLOW,
    "PaymentsToAcquirePropertyPlantAndEquipment": Statement.CASH_FLOW,
    "ProceedsFromSaleOfPropertyPlantAndEquipment": Statement.CASH_FLOW,
    "FinanceLeasePrincipalPayments": Statement.CASH_FLOW,
    "RevenueFromContractWithCustomerExcludingAssessedTax": Statement.INCOME_STATEMENT,
    "Revenues": Statement.INCOME_STATEMENT,
    "OperatingIncomeLoss": Statement.INCOME_STATEMENT,
    "ResearchAndDevelopmentExpense": Statement.INCOME_STATEMENT,
    "NetIncomeLoss": Statement.INCOME_STATEMENT,
    "IncomeTaxExpenseBenefit": Statement.INCOME_STATEMENT,
    "Depreciation": Statement.INCOME_STATEMENT,
    "DepreciationDepletionAndAmortization": Statement.INCOME_STATEMENT,
}

CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue.total": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
    ),
    "cash_flow.operating": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex.cash": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "capex.disposal_proceeds": ("ProceedsFromSaleOfPropertyPlantAndEquipment",),
    "capex.finance_lease_principal": ("FinanceLeasePrincipalPayments",),
    # Meta tags both. `Depreciation` is the narrower figure and the one
    # comparable to what the other two filers report here.
    "depreciation": ("Depreciation", "DepreciationDepletionAndAmortization"),
    "income.operating": ("OperatingIncomeLoss",),
    "balance.assets": ("Assets",),
    "balance.current_liabilities": ("LiabilitiesCurrent",),
    "balance.cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "balance.marketable_securities": ("MarketableSecuritiesCurrent",),
}

CUMULATIVE_CONCEPTS: tuple[str, ...] = ("capex.cash", "cash_flow.operating")

CAPEX_CONCEPTS = ("PaymentsToAcquirePropertyPlantAndEquipment",)

REPORTED_SEGMENTS = ("Family of Apps", "Reality Labs")


class MetaAdapter:
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
                availability=Availability.NOT_DISCLOSED,
                explanation=(
                    "Meta reports Family of Apps and Reality Labs, neither of which is an "
                    "infrastructure business. There is no segment whose revenue the data "
                    "centre spending can be divided into, so capex intensity here is not "
                    "the same measure it is at a filer that sells capacity."
                ),
                known_segments=REPORTED_SEGMENTS,
            )
        return SegmentSupport(
            availability=Availability.AVAILABLE,
            explanation=f"{source} carries dimensional facts",
            known_segments=REPORTED_SEGMENTS,
        )
