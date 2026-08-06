"""References to the evidence behind a number."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from capex_atlas.schemas.hashing import stable_id


class SourceKind(StrEnum):
    SEC_FILING = "sec_filing"
    EARNINGS_RELEASE = "earnings_release"
    TRANSCRIPT = "transcript"
    PRESENTATION = "presentation"
    STATUTE = "statute"
    THIRD_PARTY = "third_party"
    USER = "user"


class SourceReference(BaseModel):
    """A citation precise enough that a reader can check the number themselves.

    ``section``/``page``/``quote`` matter more than they look: an accession
    number alone does not let anyone verify that a filing actually says what a
    calculation claims it says.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str
    kind: SourceKind
    url: str | None = None
    accession: str | None = None
    form: str | None = None
    section: str | None = None
    page: int | None = None
    quote: str | None = None
    retrieved_at: datetime | None = None
    content_sha256: str | None = None
    parser_version: str | None = None
    license_status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _derive_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("source_id"):
            data = dict(data)
            data["source_id"] = stable_id(
                "src",
                data.get("kind"),
                data.get("url"),
                data.get("accession"),
                data.get("section"),
                data.get("page"),
                data.get("quote"),
            )
        return data

    @property
    def is_verifiable(self) -> bool:
        """Whether this reference points at a specific, checkable passage."""
        return bool(self.quote or self.section or self.page)

    def narrow(self, **overrides: Any) -> SourceReference:
        """Return a more specific citation, with a freshly derived id.

        Use this rather than ``model_copy`` when changing anything the id is
        built from. ``model_copy`` keeps the old ``source_id``, so a citation
        pointing at a different filing would silently carry the previous one and
        every fact in a bundle would appear to come from the same place.
        """
        fields = self.model_dump()
        fields.update(overrides)
        fields.pop("source_id", None)
        return SourceReference.model_validate(fields)
