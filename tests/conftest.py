from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from capex_atlas.schemas import (
    EvidenceStatus,
    FinancialFact,
    FiscalPeriod,
    SourceKind,
    SourceReference,
    Statement,
)
from capex_atlas.schemas.values import AnalyticalValue


@pytest.fixture
def period() -> FiscalPeriod:
    return FiscalPeriod(
        fiscal_year=2026,
        fiscal_quarter=2,
        start=date(2026, 4, 1),
        end=date(2026, 6, 30),
    )


@pytest.fixture
def source() -> SourceReference:
    return SourceReference(
        kind=SourceKind.SEC_FILING,
        url="https://www.sec.gov/example",
        accession="0000000000-26-000000",
        form="10-Q",
        section="Condensed Consolidated Statements of Cash Flows",
        page=6,
    )


@pytest.fixture
def fact(period: FiscalPeriod, source: SourceReference) -> FinancialFact:
    return FinancialFact(
        entity_id="EXMPL",
        metric_id="cash_flow.operating",
        value=Decimal("1000"),
        unit="USD_millions",
        period=period,
        statement=Statement.CASH_FLOW,
        source=source,
    )


def make_value(
    amount: str | None,
    *,
    status: EvidenceStatus = EvidenceStatus.REPORTED,
    unit: str = "USD_millions",
    period: FiscalPeriod | None = None,
    value_id: str = "v",
) -> AnalyticalValue:
    """Build a standalone analytical value for tests."""
    return AnalyticalValue(
        value_id=value_id,
        value=None if amount is None else Decimal(amount),
        unit=unit,
        status=status,
        period=period,
    )
