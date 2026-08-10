"""Reading and writing bundles.

Serialization is deterministic: keys sorted, no wall-clock anywhere except the
provenance block. Two runs over the same inputs therefore produce byte-identical
files apart from that block, which turns "is this reproducible" from a judgement
into a comparison.

Parquet sidecars exist so the fact and calculation tables can be queried with
DuckDB without going through Python. The JSON file is the authority; the
sidecars are a convenience and are rewritten from it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from capex_atlas.bundle.model import SCHEMA_VERSION, AnalysisBundle
from capex_atlas.disclaimer import FULL

BUNDLE_FILE = "analysis.atlas.json"
SIDECARS = {
    "facts": "facts.parquet",
    "calculations": "calculations.parquet",
    "claims": "claims.parquet",
}
DISCLAIMER_FILE = "DISCLAIMER.md"
SOURCES_FILE = "sources.json"


def canonical_json(bundle: AnalysisBundle, *, include_provenance: bool = True) -> str:
    """Serialize deterministically.

    With ``include_provenance=False`` the timestamp and package version drop out,
    leaving exactly the analytical content. That form is what a reproducibility
    check compares and what :func:`capex_atlas.bundle.diff.diff_bundles` reads.
    """
    payload: dict[str, Any] = bundle.model_dump(mode="json")
    if not include_provenance:
        payload.pop("provenance", None)
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def content_only(bundle: AnalysisBundle) -> str:
    """The analytical content, stripped of when it was produced."""
    return canonical_json(bundle, include_provenance=False)


def write_bundle(bundle: AnalysisBundle, directory: Path) -> Path:
    """Write the bundle and its sidecars into *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / BUNDLE_FILE
    target.write_text(canonical_json(bundle), encoding="utf-8")

    (directory / DISCLAIMER_FILE).write_text(FULL, encoding="utf-8")
    (directory / SOURCES_FILE).write_text(
        json.dumps(
            [source.model_dump(mode="json") for source in bundle.sources],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    _write_table(directory / SIDECARS["facts"], [f.model_dump(mode="json") for f in bundle.facts])
    _write_table(
        directory / SIDECARS["calculations"],
        [node.model_dump(mode="json") for node in bundle.calculations],
    )
    _write_table(directory / SIDECARS["claims"], [c.model_dump(mode="json") for c in bundle.claims])
    return target


class IncompatibleBundleError(ValueError):
    """The file was written by a version of the schema this code cannot read."""


def read_bundle(path: Path) -> AnalysisBundle:
    """Read a bundle from its JSON file or from the directory containing it.

    The schema version was written into every bundle and then read by nothing, so
    a file from a future major version would be parsed on a best-effort basis and
    quietly missing whatever this code does not know about. Checking it costs one
    comparison and turns a silent misreading into a refusal.
    """
    target = path / BUNDLE_FILE if path.is_dir() else path
    text = target.read_text(encoding="utf-8")
    found = json.loads(text).get("schema_version", SCHEMA_VERSION)
    if str(found).split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise IncompatibleBundleError(
            f"{target} declares bundle schema {found}; this build reads "
            f"{SCHEMA_VERSION}. Read it with the version that wrote it."
        )
    return AnalysisBundle.model_validate_json(text)


def _write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        # An empty parquet file with no schema is not readable, so skip it and
        # let the absence say there were no rows.
        path.unlink(missing_ok=True)
        return
    flattened = [_flatten(row) for row in rows]
    pl.DataFrame(flattened, strict=False).write_parquet(path)


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    """Collapse nested objects to JSON strings so the table stays columnar."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, dict | list | tuple):
            out[key] = json.dumps(value, sort_keys=True)
        else:
            out[key] = value
    return out
