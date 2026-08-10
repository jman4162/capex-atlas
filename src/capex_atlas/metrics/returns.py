"""Return on invested capital, in several named forms.

ROIC has no settled definition. Every choice below (which tax rate, which capital
base, whether to capitalize R&D, whether to average) moves the answer by
percentage points, so each variant is a separate metric with its own name rather
than a flag on one.

The tax rate arrives as a registry assumption, so a return computed with the
statutory rate comes out marked estimated. That is the correct reading: nobody
outside the company knows its marginal cash rate on incremental capital.
"""

from __future__ import annotations

from decimal import Decimal

from capex_atlas.provenance.metric import INHERIT, metric

TWO = Decimal(2)


@metric(
    metric_id="returns.nopat",
    version="1.0.0",
    formula="operating income * (1 - tax rate)",
    unit=INHERIT,
    label="net operating profit after tax",
)
def nopat(operating_income: Decimal, tax_rate: Decimal) -> Decimal:
    """Operating profit less notional tax.

    Uses a rate supplied by the caller rather than the company's effective rate,
    which is distorted by one-off items, foreign mix and share-based
    compensation in ways that have little to do with capital productivity.
    """
    return operating_income * (Decimal(1) - tax_rate)


@metric(
    metric_id="returns.invested_capital_operating",
    version="1.0.0",
    formula="total assets - current liabilities",
    unit=INHERIT,
    label="invested capital (operating basis)",
    homogeneous_inputs=True,
)
def invested_capital_operating(total_assets: Decimal, current_liabilities: Decimal) -> Decimal:
    """Capital employed, on the simplest defensible basis.

    Includes cash and marketable securities, which at cash-rich filers inflates
    the base and understates the return. Use the excess-cash variant when the
    balance sheet carries a large securities portfolio.
    """
    return total_assets - current_liabilities


@metric(
    metric_id="returns.invested_capital_ex_cash",
    version="1.0.0",
    formula="total assets - current liabilities - cash and equivalents - marketable securities",
    unit=INHERIT,
    label="invested capital (excluding cash)",
    homogeneous_inputs=True,
)
def invested_capital_ex_cash(
    total_assets: Decimal,
    current_liabilities: Decimal,
    cash: Decimal,
    marketable_securities: Decimal,
) -> Decimal:
    """Operating capital with the investment portfolio removed.

    Closer to the capital actually at work in the business, at the cost of
    treating every dollar of securities as non-operating when some is working
    capital.
    """
    return total_assets - current_liabilities - cash - marketable_securities


@metric(
    metric_id="returns.roic",
    version="1.0.0",
    formula="NOPAT / invested capital",
    unit="percent",
    label="return on invested capital",
)
def roic(nopat_value: Decimal, invested_capital: Decimal) -> Decimal:
    """Point-in-time return on the closing capital base.

    Understates returns for a company whose capital grew during the period,
    since the full closing base never earned for the whole period. Prefer the
    averaged form when the base is moving quickly.
    """
    return nopat_value / invested_capital


@metric(
    metric_id="returns.roic_average_capital",
    version="1.0.0",
    formula="NOPAT / ((opening invested capital + closing invested capital) / 2)",
    unit="percent",
    label="return on average invested capital",
    allow_mixed_periods=True,
)
def roic_on_average_capital(
    nopat_value: Decimal,
    opening_invested_capital: Decimal,
    closing_invested_capital: Decimal,
) -> Decimal:
    """The fairer denominator during a build-out."""
    return nopat_value / ((opening_invested_capital + closing_invested_capital) / TWO)


@metric(
    metric_id="returns.roic_rd_capitalized",
    version="1.0.0",
    formula=(
        "(operating income + R&D expense - R&D amortization) * (1 - tax rate) "
        "/ (invested capital + capitalized R&D asset)"
    ),
    unit="percent",
    label="return on invested capital (R&D capitalized)",
)
def roic_rd_capitalized(
    operating_income: Decimal,
    research_and_development: Decimal,
    rd_amortization: Decimal,
    invested_capital: Decimal,
    capitalized_rd_asset: Decimal,
    tax_rate: Decimal,
) -> Decimal:
    """Treats research spending as the investment it economically is.

    Accounting expenses R&D immediately, which understates both profit and
    capital at a research-heavy filer. Correcting it needs an assumed useful life
    for research, which no company discloses, so the amortization and asset
    figures are the caller's construction and this result carries their status.
    """
    adjusted_operating_income = operating_income + research_and_development - rd_amortization
    adjusted_capital = invested_capital + capitalized_rd_asset
    return (adjusted_operating_income * (Decimal(1) - tax_rate)) / adjusted_capital


@metric(
    metric_id="returns.incremental_roic",
    version="1.0.0",
    formula="(NOPAT_t - NOPAT_{t-n}) / (invested capital_{t-1} - invested capital_{t-n-1})",
    unit="percent",
    label="incremental return on invested capital",
    allow_mixed_periods=True,
)
def incremental_roic(
    nopat_now: Decimal,
    nopat_then: Decimal,
    capital_now: Decimal,
    capital_then: Decimal,
) -> Decimal:
    """Return on capital added between two periods.

    The marginal figure, and usually far from the average one. It is also the
    noisiest metric here: any lag choice is arbitrary, and a denominator near
    zero sends it to absurd values, which the kernel reports as unresolved
    rather than as a large number.
    """
    return (nopat_now - nopat_then) / (capital_now - capital_then)
