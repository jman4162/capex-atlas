"""The disclaimer must stay identical everywhere it appears.

A disclaimer is only worth the places a reader actually meets it, so the same
text has to reach the docs, the CLI and every exported analysis. Generating all
of them from one constant makes drift a build failure rather than something
nobody notices for a year.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capex_atlas.disclaimer import DOCUMENT, FULL, SHORT

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_disclaimer_document_matches_the_module() -> None:
    on_disk = (REPO_ROOT / "DISCLAIMER.md").read_text()
    assert on_disk == DOCUMENT, (
        "DISCLAIMER.md has drifted from capex_atlas.disclaimer. Regenerate it:\n"
        '  uv run python -c "from capex_atlas.disclaimer import DOCUMENT; '
        "from pathlib import Path; Path('DISCLAIMER.md').write_text(DOCUMENT)\""
    )


def flattened(text: str) -> str:
    """Lowercase and stripped of Markdown, so formatting cannot hide a phrase.

    Bold markers, blockquote prefixes and line wrapping all fall out, which
    matters because the README carries its disclaimer inside a wrapped
    blockquote and a naive substring search misses it.
    """
    lines = [line.lstrip().removeprefix(">").strip() for line in text.lower().splitlines()]
    return " ".join(" ".join(lines).replace("*", "").split())


@pytest.mark.parametrize(
    "phrase",
    [
        "is investment, legal, tax, accounting or other professional advice",
        "no ratings, no price targets",
        'provided "as is"',
        "without warranties of any kind",
        "accept no liability",
        "trading or investment losses",
        "at your own risk",
        "not affiliated with, endorsed by",
        "not forecasts, projections or predictions",
    ],
)
def test_full_text_covers_the_required_ground(phrase: str) -> None:
    assert phrase in flattened(FULL), f"disclaimer no longer says {phrase!r}"


def test_short_form_names_all_four_advice_types() -> None:
    for kind in ("investment", "legal", "tax", "accounting"):
        assert kind in SHORT.lower()


def test_short_form_fits_a_chart_footer() -> None:
    assert len(SHORT) <= 200


def test_readme_carries_the_disclaimer_and_links_the_document() -> None:
    readme = flattened((REPO_ROOT / "README.md").read_text())
    assert "disclaimer.md" in readme
    assert "not investment, legal, tax or accounting advice" in readme
    assert "no liability" in readme
