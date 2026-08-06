"""Domain event log.

Distinct from OTEL tracing on purpose. Traces describe runtime behaviour and may
be sampled or expire; these events describe analytical state changes and are part
of the reproducible record -- they answer "who approved this mapping, on what
evidence, at which package version".
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    SOURCE_ADDED = "source_added"
    FACT_EXTRACTED = "fact_extracted"
    FACT_RECONCILED = "fact_reconciled"
    MAPPING_PROPOSED = "mapping_proposed"
    MAPPING_APPROVED = "mapping_approved"
    CLAIM_ADDED = "claim_added"
    SCENARIO_RUN = "scenario_run"
    REPORT_PUBLISHED = "report_published"


class AtlasEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    run_id: str
    event_type: EventType
    object_id: str
    actor: str
    """``user:<name>``, ``agent:<name>`` or ``system``. Never blank -- an
    unattributed approval is not an approval."""

    timestamp: datetime
    package_version: str
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
