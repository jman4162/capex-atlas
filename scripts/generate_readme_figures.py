"""Render the committed example's charts to static SVG for the README.

The figures come from the bundle's own ``ChartSpec``s through the same renderer
the app uses, so a README figure cannot disagree with the code that produced it.
CI regenerates them and fails on drift, exactly as it does for the bundle.

SVG rather than PNG: it is text, so a diff shows what changed, and it stays sharp
at any width.

    uv run python scripts/generate_readme_figures.py
"""

from __future__ import annotations

from pathlib import Path

from capex_atlas.application import AtlasApplication
from capex_atlas.bundle.charts import CAPEX_VS_DEPRECIATION, EVIDENCE_MIX, VINTAGE_CASH_FLOW
from capex_atlas.viz.svg import render_svg

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples" / "googl-2025fy"
TARGET = REPO_ROOT / "docs" / "_static"

FIGURES = {
    EVIDENCE_MIX: "evidence-mix.svg",
    CAPEX_VS_DEPRECIATION: "capex-vs-depreciation.svg",
    VINTAGE_CASH_FLOW: "vintage-cash-flow.svg",
}


def write_figure(figure: dict, path: Path) -> None:
    """Write one figure dictionary as SVG, deterministically.

    Uses the package's own writer rather than Plotly's image export, which needs
    Kaleido and whose bytes shift between versions. These files are committed and
    CI fails on drift, so the output has to be stable.
    """
    path.write_text(render_svg(figure), encoding="utf-8")


def build() -> list[Path]:
    if not (EXAMPLE / "analysis.atlas.json").exists():
        raise SystemExit(
            f"no example bundle at {EXAMPLE}. Build it first:\n"
            "  uv run python scripts/build_example.py"
        )
    TARGET.mkdir(parents=True, exist_ok=True)
    app = AtlasApplication.from_path(EXAMPLE)

    written: list[Path] = []
    for data_ref, filename in FIGURES.items():
        figure = app.figure(data_ref)
        if figure is None:
            raise SystemExit(
                f"the example bundle carries no chart for {data_ref!r}. "
                "Rebuild it with scripts/build_example.py."
            )
        path = TARGET / filename
        write_figure(figure, path)
        written.append(path)
    return written


if __name__ == "__main__":
    for path in build():
        size = path.stat().st_size / 1024
        print(f"wrote {path.relative_to(REPO_ROOT)} ({size:.0f} KB)")
