from __future__ import annotations

import itertools

import pytest

from capex_atlas.schemas.evidence import EvidenceStatus

ORDER = [
    EvidenceStatus.REPORTED,
    EvidenceStatus.DERIVED,
    EvidenceStatus.ESTIMATED,
    EvidenceStatus.SCENARIO,
    EvidenceStatus.UNRESOLVED,
]


def test_strength_order_is_strict():
    ranks = [status.rank for status in ORDER]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)


@pytest.mark.parametrize(("left", "right"), list(itertools.combinations(ORDER, 2)))
def test_weakest_picks_the_later_status(left: EvidenceStatus, right: EvidenceStatus):
    assert EvidenceStatus.weakest(left, right) is right
    assert EvidenceStatus.weakest(right, left) is right


def test_weakest_is_order_independent():
    statuses = [EvidenceStatus.SCENARIO, EvidenceStatus.REPORTED, EvidenceStatus.ESTIMATED]
    for permutation in itertools.permutations(statuses):
        assert EvidenceStatus.weakest(*permutation) is EvidenceStatus.SCENARIO


def test_unresolved_dominates():
    # A calculation depending on something undetermined is undetermined, not
    # merely estimated.
    assert (
        EvidenceStatus.weakest(EvidenceStatus.REPORTED, EvidenceStatus.UNRESOLVED)
        is EvidenceStatus.UNRESOLVED
    )


def test_every_status_has_a_distinct_glyph():
    glyphs = [status.glyph for status in ORDER]
    assert len(set(glyphs)) == len(glyphs)
