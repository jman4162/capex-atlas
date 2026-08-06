"""The analysis bundle: build it, write it, audit it, diff it."""

from capex_atlas.bundle.audit import AuditFinding, AuditReport, Severity, audit_bundle
from capex_atlas.bundle.builder import UnsupportedEntityError, build_analysis, headline_table
from capex_atlas.bundle.diff import BundleDiff, Change, ChangeKind, diff_bundles
from capex_atlas.bundle.io import (
    BUNDLE_FILE,
    canonical_json,
    content_only,
    read_bundle,
    write_bundle,
)
from capex_atlas.bundle.model import AnalysisBundle, BundleProvenance

__all__ = [
    "BUNDLE_FILE",
    "AnalysisBundle",
    "AuditFinding",
    "AuditReport",
    "BundleDiff",
    "BundleProvenance",
    "Change",
    "ChangeKind",
    "Severity",
    "UnsupportedEntityError",
    "audit_bundle",
    "build_analysis",
    "canonical_json",
    "content_only",
    "diff_bundles",
    "headline_table",
    "read_bundle",
    "write_bundle",
]
