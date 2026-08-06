"""Trim a live SEC Company Facts payload into a committed test fixture.

Fixtures are hash-pinned so tests never reach the network and a filing revision
cannot silently change a test's meaning. Rebuilding one is a deliberate act.

    uv run python scripts/build_fixture.py GOOGL 1652044
    uv run python scripts/build_fixture.py MSFT 789019
    uv run python scripts/build_fixture.py META 1326801

Requires CAPEX_ATLAS_SEC_USER_AGENT, like every other path that reaches SEC.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from capex_atlas.adapters import adapter_for
from capex_atlas.sources.raw import RawStore
from capex_atlas.sources.sec import SecClient

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
CUTOFF = "2023-01-01"
"""Keep three years or so. Enough history to chart, small enough to review."""


def concepts_for(entity_id: str) -> set[str]:
    """Every tag the adapter can ask for, so the fixture covers its own adapter."""
    adapter = adapter_for(entity_id)
    wanted = set(adapter.statement_map())
    for tags in adapter.concept_aliases().values():
        wanted.update(tags)
    return wanted


def trim(payload: dict, entity_id: str) -> dict:
    wanted = concepts_for(entity_id)
    gaap = payload["facts"]["us-gaap"]
    kept: dict[str, dict] = {}
    for concept in sorted(wanted):
        body = gaap.get(concept)
        if body is None:
            continue
        units = {}
        for unit, entries in body.get("units", {}).items():
            recent = [entry for entry in entries if entry["end"] >= CUTOFF]
            if recent:
                units[unit] = sorted(recent, key=lambda e: (e["end"], e.get("filed", "")))
        if units:
            kept[concept] = {"units": units}
    return {
        "cik": payload["cik"],
        "entityName": payload["entityName"],
        "facts": {"us-gaap": kept},
    }


def build(entity_id: str, cik: int) -> Path:
    store = RawStore(REPO_ROOT / "data" / "raw")
    with SecClient(store=store) as client:
        _, payload = client.company_facts(cik, entity_id)

    document = trim(payload, entity_id)
    target = FIXTURES / f"{entity_id.lower()}_companyfacts_trimmed.json"
    body = json.dumps(document, indent=1, sort_keys=True) + "\n"
    target.write_text(body, encoding="utf-8")

    manifest_path = FIXTURES / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest[target.name] = {
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
        "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
        "entity": document["entityName"],
        "cik": document["cik"],
        "license": "public domain (SEC EDGAR)",
        "trimmed": (
            f"us-gaap only; {len(document['facts']['us-gaap'])} concepts the "
            f"{entity_id} adapter references; periods ending on or after {CUTOFF}"
        ),
    }
    manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), indent=2) + "\n")
    return target


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    ticker, cik_text = sys.argv[1].upper(), sys.argv[2]
    written = build(ticker, int(cik_text))
    size = written.stat().st_size / 1024
    print(f"wrote {written.relative_to(REPO_ROOT)} ({size:.0f} KB)")
