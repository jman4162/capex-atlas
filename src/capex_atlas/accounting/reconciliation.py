"""Accounting identities that must hold before anything is modelled.

A dataset that fails these is not a dataset with a small error in it; it is one
whose extraction is wrong somewhere, and every metric built on it inherits the
fault. Running them first turns a class of silent corruption into a visible
failure.

Tolerances exist because filers round to millions and the identity then misses by
a rounding unit. They are absolute, in the unit of the facts being checked, and
deliberately tight.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from capex_atlas.schemas.facts import FinancialFact
from capex_atlas.schemas.period import PeriodKind


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    """Inputs were absent. Not a pass: nothing was verified."""


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    check: str
    status: CheckStatus
    period_label: str | None = None
    detail: str = ""
    difference: Decimal | None = None

    @property
    def ok(self) -> bool:
        return self.status is not CheckStatus.FAILED


class ReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.ok for result in self.results)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is CheckStatus.FAILED)

    @property
    def verified_count(self) -> int:
        """Checks that actually ran. Skips are not evidence of correctness."""
        return sum(1 for r in self.results if r.status is CheckStatus.PASSED)


def _index(facts: Sequence[FinancialFact]) -> dict[tuple[str, str], FinancialFact]:
    return {(f.metric_id, f.period.label): f for f in facts}


def check_balance_sheet(
    facts: Sequence[FinancialFact], *, tolerance: Decimal = Decimal("1")
) -> list[CheckResult]:
    """Assets equal liabilities plus equity, at every reported date."""
    index = _index(facts)
    labels = sorted(
        {
            f.period.label
            for f in facts
            if f.metric_id in ("Assets", "Liabilities", "StockholdersEquity")
        }
    )
    results: list[CheckResult] = []
    for label in labels:
        assets = index.get(("Assets", label))
        liabilities = index.get(("Liabilities", label))
        equity = index.get(("StockholdersEquity", label))
        if not (assets and liabilities and equity):
            results.append(
                CheckResult(
                    check="balance_sheet_identity",
                    status=CheckStatus.SKIPPED,
                    period_label=label,
                    detail="one of assets, liabilities or equity is missing",
                )
            )
            continue
        difference = assets.value - (liabilities.value + equity.value)
        passed = abs(difference) <= tolerance
        results.append(
            CheckResult(
                check="balance_sheet_identity",
                status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                period_label=label,
                difference=difference,
                detail=(
                    ""
                    if passed
                    else (
                        f"assets {assets.value} != liabilities {liabilities.value} "
                        f"+ equity {equity.value}"
                    )
                ),
            )
        )
    return results


def check_year_to_date_consistency(
    facts: Sequence[FinancialFact],
    concept: str,
    *,
    tolerance: Decimal = Decimal("1"),
) -> list[CheckResult]:
    """Cumulative figures increase monotonically in magnitude within a year.

    A nine-month total smaller than the six-month total means the two came from
    different bases, which is usually a sign that periods were misassigned.
    Sign is taken into account because outflow concepts are reported negative by
    some filers and positive by others.
    """
    cumulative = [f for f in facts if f.metric_id == concept and _cumulative_index(f) is not None]
    results: list[CheckResult] = []
    if not cumulative:
        # Report the absence. A check that silently examines nothing is worse
        # than no check, because the green result implies verification.
        return [
            CheckResult(
                check="ytd_monotonic",
                status=CheckStatus.SKIPPED,
                detail=f"{concept}: no cumulative periods found",
            )
        ]

    years = sorted({f.period.fiscal_year for f in cumulative})
    for year in years:
        series = sorted(
            (f for f in cumulative if f.period.fiscal_year == year),
            key=lambda f: _cumulative_index(f) or 0,
        )
        if len(series) < 2:
            results.append(
                CheckResult(
                    check="ytd_monotonic",
                    status=CheckStatus.SKIPPED,
                    period_label=f"{year}",
                    detail=f"{concept}: fewer than two cumulative points",
                )
            )
            continue
        for earlier, later in itertools.pairwise(series):
            grew = abs(later.value) + tolerance >= abs(earlier.value)
            results.append(
                CheckResult(
                    check="ytd_monotonic",
                    status=CheckStatus.PASSED if grew else CheckStatus.FAILED,
                    period_label=later.period.label,
                    difference=abs(later.value) - abs(earlier.value),
                    detail=(
                        ""
                        if grew
                        else (
                            f"{concept} cumulative fell from {earlier.value} "
                            f"({earlier.period.label}) to {later.value} ({later.period.label})"
                        )
                    ),
                )
            )
    return results


def _cumulative_index(fact: FinancialFact) -> int | None:
    """How many quarters a cumulative fact covers, or ``None`` if it is not one.

    A filer's year-to-date sequence runs Q1, half-year, nine months, full year.
    The first quarter is both discrete and cumulative, which is why it opens the
    series; a standalone Q2 or Q3 is discrete only and takes no part.
    """
    period = fact.period
    if period.kind is PeriodKind.FISCAL_YEAR:
        return 4
    if period.kind is PeriodKind.YEAR_TO_DATE:
        return period.fiscal_quarter
    if period.kind is PeriodKind.QUARTER and period.fiscal_quarter == 1:
        return 1
    return None


def reconcile(
    facts: Sequence[FinancialFact],
    *,
    cumulative_concepts: Sequence[str] = (),
    tolerance: Decimal = Decimal("1"),
) -> ReconciliationReport:
    """Run every identity that the supplied facts can support."""
    results = list(check_balance_sheet(facts, tolerance=tolerance))
    for concept in cumulative_concepts:
        results.extend(check_year_to_date_consistency(facts, concept, tolerance=tolerance))
    return ReconciliationReport(results=tuple(results))
