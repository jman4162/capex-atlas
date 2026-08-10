"""The committed example must stay honest.

A worked example that has drifted from the code is worse than none: readers
trust it precisely because it is checked in. So CI rebuilds it from the pinned
fixture, compares, and audits the result.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from capex_atlas.assumptions.registry import AssumptionRegistry
from capex_atlas.bundle.audit import audit_bundle
from capex_atlas.bundle.io import BUNDLE_FILE, content_only, read_bundle
from capex_atlas.schemas.evidence import EvidenceStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "examples" / "googl-2025fy"

sys.path.insert(0, str(REPO_ROOT / "scripts"))


@pytest.fixture(scope="module")
def committed():  # type: ignore[no-untyped-def]
    if not (EXAMPLE / BUNDLE_FILE).exists():
        pytest.fail(
            f"no example bundle at {EXAMPLE}. Rebuild it:\n  uv run python scripts/build_example.py"
        )
    return read_bundle(EXAMPLE)


def test_the_example_rebuilds_to_the_same_content(committed, tmp_path: Path):  # type: ignore[no-untyped-def]
    import build_example
    from build_example import illustrative_scenario  # noqa: F401

    original_target = build_example.TARGET
    build_example.TARGET = tmp_path / "rebuilt"
    try:
        rebuilt = read_bundle(build_example.build())
    finally:
        build_example.TARGET = original_target

    assert content_only(rebuilt) == content_only(committed), (
        "the committed example no longer matches what the code produces. "
        "Rebuild it deliberately: uv run python scripts/build_example.py"
    )


def test_the_example_audits_clean(committed):  # type: ignore[no-untyped-def]
    report = audit_bundle(committed)
    assert report.passed, [str(finding) for finding in report.errors]
    assert report.values_checked >= 14


def test_the_example_carries_a_scenario_and_it_is_audited(committed):  # type: ignore[no-untyped-def]
    assert len(committed.scenarios) == 1
    scenario = committed.scenarios[0]
    # Scenario figures are published figures; they get walked like the rest.
    # Unresolved is permitted: a vintage that never pays back has no payback,
    # and saying so beats inventing one.
    allowed = {EvidenceStatus.SCENARIO, EvidenceStatus.UNRESOLVED}
    assert all(value.status in allowed for value in scenario.values)
    assert any(value.status is EvidenceStatus.SCENARIO for value in scenario.values)
    for value in scenario.values:
        assert committed.node(value.formula_node_id or "") is not None


def test_the_scenario_names_the_assumptions_it_rests_on(committed):  # type: ignore[no-untyped-def]
    """Naming them is not enough; they have to be findable.

    This test used to assert the presence of the literal string
    `useful_life.servers_and_network.googl`, which resolves in no registry -- so
    it pinned a dangling citation in place rather than catching it. Assert that
    every id resolves instead, which is the property a reader depends on.
    """
    ids = committed.scenarios[0].definition.assumption_ids
    assert "tax.us_federal_statutory_rate" in ids
    for assumption_id in ids:
        assert committed.assumption(assumption_id) is not None, (
            f"the scenario cites {assumption_id}, which the bundle does not carry"
        )
        assert AssumptionRegistry.load().get(assumption_id) is not None


def test_the_example_states_it_is_not_an_estimate(committed):  # type: ignore[no-untyped-def]
    description = committed.scenarios[0].definition.description
    assert "not an estimate" in description.lower()


def test_the_example_is_small_enough_to_review(committed):  # type: ignore[no-untyped-def]
    size_kb = (EXAMPLE / BUNDLE_FILE).stat().st_size / 1024
    assert size_kb < 250, f"{size_kb:.0f} KB is too large for a reviewable example"


def test_the_example_carries_its_disclaimer(committed):  # type: ignore[no-untyped-def]
    assert committed.disclaimer.strip()
    assert (EXAMPLE / "DISCLAIMER.md").exists()


def test_the_example_reconciles(committed):  # type: ignore[no-untyped-def]
    assert committed.validation is not None
    assert committed.validation.passed
    assert committed.validation.verified_count > 0


class TestTheExampleCarriesItsCharts:
    """The chart grammar had no caller for a whole release. It has one now."""

    def test_specs_are_attached(self, committed):  # type: ignore[no-untyped-def]
        refs = {spec.data_ref for spec in committed.charts}
        assert {"evidence_mix", "capex_vs_depreciation", "vintage_cash_flow"} <= refs

    def test_every_spec_names_its_status_column(self, committed):  # type: ignore[no-untyped-def]
        # Without it a renderer cannot tell a scenario from a measurement.
        for spec in committed.charts:
            assert spec.value_status_field, spec.data_ref

    def test_every_spec_renders(self, committed):  # type: ignore[no-untyped-def]
        from capex_atlas.application import AtlasApplication

        app = AtlasApplication(committed)
        for spec in committed.charts:
            assert app.figure(spec.data_ref) is not None, spec.data_ref

    def test_the_committed_figures_match_the_bundle(self, committed):  # type: ignore[no-untyped-def]
        import sys

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import generate_readme_figures as figures

        from capex_atlas.application import AtlasApplication
        from capex_atlas.viz.svg import render_svg

        app = AtlasApplication(committed)
        for data_ref, filename in figures.FIGURES.items():
            path = REPO_ROOT / "docs" / "_static" / filename
            assert path.exists(), f"{filename} is missing; run generate_readme_figures.py"
            expected = render_svg(app.figure(data_ref))
            assert path.read_text() == expected, (
                f"{filename} has drifted from the bundle. "
                "Regenerate: uv run python scripts/generate_readme_figures.py"
            )


def test_node_ids_are_stable_across_kernel_changes(committed):  # type: ignore[no-untyped-def]
    """Content addresses are only useful if they survive refactoring.

    A stored bundle names its calculations by hash. If the kernel changes how it
    derives them, every citation into every published bundle silently points at
    nothing. This pins the fourteen ids the committed example carries, so a change
    to the derivation has to be a deliberate migration rather than a side effect.

    The keyword-binding fix was chosen partly to keep this list intact: binding
    arguments to their declared positions changes which calls collide without
    changing what any existing call hashes to.
    """
    ids = sorted(node.node_id for node in committed.calculations)
    assert ids == [
        "calc:1bed0f31ce7e1155",
        "calc:1e8f864677c3cce4",
        "calc:2593047f3f99dd64",
        "calc:2b9bcd056cd30653",
        "calc:63d6da11626ba701",
        "calc:6cf5d72b75ed0536",
        "calc:a0cbf733679405fb",
        "calc:abf7ef5c7ec2c14c",
        "calc:c0355abbdd37d413",
        "calc:de67f4477a9ebb1f",
        "calc:e8e175aea4d02ed7",
        "calc:ede130ecd087e331",
        "calc:ef6ebc84a3bd57b5",
        "calc:ff3e47717df969e5",
    ]
