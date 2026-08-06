"""XBRL fact extraction. SEC Company Facts now; Arelle behind the [xbrl] extra later."""

from capex_atlas.xbrl.companyfacts import (
    ExtractionResult,
    Restatement,
    SkippedEntry,
    extract_facts,
)

__all__ = [
    "ExtractionResult",
    "Restatement",
    "SkippedEntry",
    "extract_facts",
]
