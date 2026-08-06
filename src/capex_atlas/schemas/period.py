"""Fiscal period identity.

Period confusion is one of the named auto-reject conditions for this project:
comparing a quarter against a trailing-twelve-month figure, or a fiscal year
against a calendar year, produces numbers that look reasonable and are wrong.
Periods are therefore a typed value, not a string passed around by hand.
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class PeriodKind(StrEnum):
    QUARTER = "Q"
    YEAR_TO_DATE = "YTD"
    TRAILING_TWELVE = "TTM"
    FISCAL_YEAR = "FY"
    INSTANT = "INSTANT"
    """A balance-sheet date rather than a span."""


_LABEL = re.compile(
    r"^(?P<year>\d{4})"
    r"(?:Q(?P<quarter>[1-4])|(?P<fy>FY)|YTD(?P<ytdq>[1-4])|TTM(?P<ttmq>[1-4])|@(?P<instant>[1-4]))$"
)


class FiscalPeriod(BaseModel):
    """A company's own fiscal period, not a calendar one.

    ``fiscal_year``/``fiscal_quarter`` follow the filer's calendar, so Microsoft's
    2026Q2 and Alphabet's 2026Q2 are different spans of real time. ``start`` and
    ``end`` carry the actual dates when known.
    """

    model_config = ConfigDict(frozen=True)

    fiscal_year: int
    fiscal_quarter: int | None = None
    kind: PeriodKind = PeriodKind.QUARTER
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        needs_quarter = (PeriodKind.QUARTER, PeriodKind.YEAR_TO_DATE, PeriodKind.TRAILING_TWELVE)
        if self.kind in needs_quarter and self.fiscal_quarter is None:
            raise ValueError(f"{self.kind} period requires a fiscal_quarter")
        if self.fiscal_quarter is not None and not 1 <= self.fiscal_quarter <= 4:
            raise ValueError(f"fiscal_quarter out of range: {self.fiscal_quarter}")
        if self.start and self.end and self.start > self.end:
            raise ValueError(f"period starts after it ends: {self.start} > {self.end}")
        return self

    @property
    def label(self) -> str:
        """Round-trippable short form, e.g. ``2026Q2``, ``2026FY``, ``2026TTM2``."""
        match self.kind:
            case PeriodKind.QUARTER:
                return f"{self.fiscal_year}Q{self.fiscal_quarter}"
            case PeriodKind.FISCAL_YEAR:
                return f"{self.fiscal_year}FY"
            case PeriodKind.YEAR_TO_DATE:
                return f"{self.fiscal_year}YTD{self.fiscal_quarter}"
            case PeriodKind.TRAILING_TWELVE:
                return f"{self.fiscal_year}TTM{self.fiscal_quarter}"
            case PeriodKind.INSTANT:
                return f"{self.fiscal_year}@{self.fiscal_quarter}"

    @classmethod
    def parse(cls, label: str) -> Self:
        """Inverse of :attr:`label`."""
        match = _LABEL.match(label.strip().upper())
        if match is None:
            raise ValueError(f"unrecognized period label: {label!r}")
        year = int(match["year"])
        if match["quarter"]:
            return cls(fiscal_year=year, fiscal_quarter=int(match["quarter"]))
        if match["fy"]:
            return cls(fiscal_year=year, kind=PeriodKind.FISCAL_YEAR)
        if match["ytdq"]:
            return cls(
                fiscal_year=year,
                fiscal_quarter=int(match["ytdq"]),
                kind=PeriodKind.YEAR_TO_DATE,
            )
        if match["ttmq"]:
            return cls(
                fiscal_year=year,
                fiscal_quarter=int(match["ttmq"]),
                kind=PeriodKind.TRAILING_TWELVE,
            )
        return cls(
            fiscal_year=year,
            fiscal_quarter=int(match["instant"]),
            kind=PeriodKind.INSTANT,
        )

    def __str__(self) -> str:
        return self.label
