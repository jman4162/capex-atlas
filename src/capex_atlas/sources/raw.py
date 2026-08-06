"""The immutable raw evidence layer.

Downloaded artifacts are written once and never edited. Everything downstream is
a transformation of these bytes, so a reader can re-derive any published number
from the same inputs, and a changed filing shows up as a new artifact rather than
as a silent difference in yesterday's analysis.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from capex_atlas.schemas.source import SourceKind, SourceReference

MANIFEST_NAME = "manifest.json"


class ArtifactConflictError(RuntimeError):
    """A stored artifact already exists at this path with different content."""


class RawArtifact(BaseModel):
    """One downloaded file and everything needed to trust it later."""

    model_config = ConfigDict(frozen=True)

    relative_path: str
    sha256: str
    byte_count: int
    retrieved_at: datetime
    url: str
    kind: SourceKind
    entity_id: str
    period_label: str | None = None
    accession: str | None = None
    form: str | None = None
    document_type: str | None = None
    license_status: str = "public_domain_sec"
    parser_version: str | None = None

    def to_source_reference(self, **overrides: object) -> SourceReference:
        """Cite this artifact. Callers add ``section``/``page``/``quote``."""
        fields: dict[str, object] = {
            "kind": self.kind,
            "url": self.url,
            "accession": self.accession,
            "form": self.form,
            "retrieved_at": self.retrieved_at,
            "content_sha256": self.sha256,
            "parser_version": self.parser_version,
            "license_status": self.license_status,
        }
        fields.update(overrides)
        return SourceReference.model_validate(fields)


class RawStore:
    """Content-addressed-ish storage under ``data/raw/<kind>/<entity>/<period>/``."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(
        self, kind: SourceKind, entity_id: str, period_label: str | None, name: str
    ) -> Path:
        parts = [kind.value, entity_id]
        if period_label:
            parts.append(period_label)
        return self.root.joinpath(*parts, name)

    def store(
        self,
        content: bytes,
        *,
        name: str,
        url: str,
        kind: SourceKind,
        entity_id: str,
        period_label: str | None = None,
        accession: str | None = None,
        form: str | None = None,
        document_type: str | None = None,
        parser_version: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> RawArtifact:
        """Write *content* and record it in the directory manifest.

        Re-storing identical bytes is a no-op that returns the existing record.
        Re-storing different bytes at the same path raises: an artifact that
        changed underneath us is a new artifact and needs its own name.
        """
        target = self.path_for(kind, entity_id, period_label, name)
        digest = hashlib.sha256(content).hexdigest()

        if target.exists():
            existing_digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if existing_digest != digest:
                raise ArtifactConflictError(
                    f"{target} already holds different content "
                    f"(stored {existing_digest[:12]}, incoming {digest[:12]}). "
                    "Raw artifacts are immutable; store the new version under a new name."
                )
            recorded = self._read_manifest(target.parent).get(name)
            if recorded is not None:
                return RawArtifact.model_validate(recorded)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        artifact = RawArtifact(
            relative_path=str(target.relative_to(self.root)),
            sha256=digest,
            byte_count=len(content),
            retrieved_at=retrieved_at or datetime.now(UTC),
            url=url,
            kind=kind,
            entity_id=entity_id,
            period_label=period_label,
            accession=accession,
            form=form,
            document_type=document_type,
            parser_version=parser_version,
        )
        self._write_manifest_entry(target.parent, name, artifact)
        return artifact

    def read(self, artifact: RawArtifact) -> bytes:
        """Return the stored bytes, verifying they still match the recorded hash."""
        path = self.root / artifact.relative_path
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != artifact.sha256:
            raise ArtifactConflictError(
                f"{path} no longer matches its recorded hash. The raw layer has been "
                "edited, which invalidates every analysis derived from it."
            )
        return content

    def manifest(
        self, kind: SourceKind, entity_id: str, period_label: str | None
    ) -> list[RawArtifact]:
        directory = self.path_for(kind, entity_id, period_label, MANIFEST_NAME).parent
        return [
            RawArtifact.model_validate(entry) for entry in self._read_manifest(directory).values()
        ]

    def _read_manifest(self, directory: Path) -> dict[str, dict[str, object]]:
        path = directory / MANIFEST_NAME
        if not path.exists():
            return {}
        loaded: dict[str, dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def _write_manifest_entry(self, directory: Path, name: str, artifact: RawArtifact) -> None:
        entries = self._read_manifest(directory)
        entries[name] = artifact.model_dump(mode="json")
        path = directory / MANIFEST_NAME
        path.write_text(
            json.dumps(dict(sorted(entries.items())), indent=2) + "\n", encoding="utf-8"
        )

    @classmethod
    def default(cls) -> Self:
        return cls(Path("data") / "raw")
