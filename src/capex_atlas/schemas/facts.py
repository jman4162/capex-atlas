"""The normalized fact layer.

A ``FinancialFact`` is something a filing says. It is immutable: adapters,
metrics and agents may all read it, and none of them may rewrite it. Analytical
judgement about what a fact *means* lives in mappings and calculations, never
here.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.hashing import stable_id
from capex_atlas.schemas.period import FiscalPeriod
from capex_atlas.schemas.source import SourceReference


class Statement(StrEnum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    SEGMENT = "segment"
    OPERATIONAL = "operational"
    """Non-financial disclosures: capacity, headcount, backlog units."""


class FinancialFact(BaseModel):
    """One reported number, with everything needed to find it again."""

    model_config = ConfigDict(frozen=True)

    fact_id: str = ""
    entity_id: str
    """Ticker or CIK; whichever the ingestion layer canonicalizes to."""

    metric_id: str
    """Canonical concept name in the Atlas ontology, not the filer's wording."""

    value: Decimal
    unit: str
    period: FiscalPeriod
    statement: Statement

    status: EvidenceStatus = EvidenceStatus.REPORTED
    is_company_non_gaap: bool = False
    """True when the filer reported it under their own definition.

    Such a value is genuinely reported -- the company said it -- but it is not
    comparable across filers without normalization, which is why it is flagged
    separately rather than demoted to a weaker status.
    """

    source: SourceReference
    xbrl_concept: str | None = None
    company_term: str | None = None
    """The filer's own words, preserved even after mapping to ``metric_id``."""

    dimensions: dict[str, str] = Field(default_factory=dict)
    extraction_method: str = "xbrl_companyfacts"
    confidence: float = 1.0

    @model_validator(mode="before")
    @classmethod
    def _derive_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("fact_id"):
            period = data.get("period")
            period_label = period.label if isinstance(period, FiscalPeriod) else period
            data = dict(data)
            data["fact_id"] = stable_id(
                "fact",
                data.get("entity_id"),
                data.get("metric_id"),
                period_label,
                data.get("unit"),
                data.get("dimensions") or {},
                data.get("xbrl_concept"),
            )
        return data
