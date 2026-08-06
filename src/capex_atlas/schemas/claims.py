"""The claim ledger.

Management commentary drives hyperscaler analysis, but it is not a financial
fact and must not sit in the same table as one. The ledger keeps four things
apart: what the statements report, what management said, what the model derives,
and what the analyst believes.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from capex_atlas.schemas.period import FiscalPeriod
from capex_atlas.schemas.source import SourceReference


class ClaimType(StrEnum):
    DEMAND = "demand"
    CAPACITY = "capacity"
    PRICING = "pricing"
    MARGIN = "margin"
    PAYBACK = "payback"
    ASSET_LIFE = "asset_life"
    CAPITAL_ALLOCATION = "capital_allocation"
    CUSTOMER_CONTRACT = "customer_contract"
    GUIDANCE = "guidance"


class VerificationStatus(StrEnum):
    REPORTED_STATEMENT = "reported_statement"
    """Management said it; no independent check attempted."""

    PARTIALLY_RECONCILABLE = "partially_reconcilable"
    INDEPENDENTLY_RECONCILABLE = "independently_reconcilable"
    NOT_PUBLICLY_VERIFIABLE = "not_publicly_verifiable"
    CONTRADICTED = "contradicted"


class ManagementClaim(BaseModel):
    """Something a person said on the record, with what can be checked about it."""

    model_config = ConfigDict(frozen=True)

    claim_id: str
    entity_id: str
    period: FiscalPeriod

    speaker: str
    claim_text: str
    claim_type: ClaimType

    evidence: SourceReference
    numeric_parameters: dict[str, Decimal] = Field(default_factory=dict)
    """Parameters the claim implies, ready to be fed to a scenario."""

    interpretation: str | None = None
    verification_status: VerificationStatus = VerificationStatus.REPORTED_STATEMENT
    undisclosed_inputs: tuple[str, ...] = ()
    """What the claim depends on that the company did not publish.

    This field is the honest half of claim analysis and should rarely be empty.
    """

    confidence: float = 1.0
    requires_review: bool = True
