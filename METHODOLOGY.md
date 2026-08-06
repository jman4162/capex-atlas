# Methodology

What the package computes, what it declines to compute, and why. Read
[DISCLAIMER.md](DISCLAIMER.md) first: nothing here is investment, legal, tax or accounting advice,
and none of it carries a warranty of accuracy.

## Epistemic status

Every figure carries one of five statuses, and every calculation degrades to its weakest input.

| glyph | status | meaning |
|---|---|---|
| ● | reported | Stated by the company in a filing or release. |
| ◆ | derived | Computed deterministically from reported values alone. |
| ▲ | estimated | Depends on a judgement the company did not disclose. |
| ○ | scenario | Depends on a user-chosen assumption; a what-if, not a measurement. |
| ! | unresolved | Could not be determined from available evidence. |

Three consequences are worth stating plainly, because each is a place where a more convenient choice
was available.

A calculation is never itself *reported*, however solid its inputs. Combining two disclosed figures
produces a derived number, because the combination is the analyst's choice and not the company's
statement.

A calculation touching anything undetermined comes out undetermined rather than defaulting to zero.
A missing input and a zero input are different claims about the world, and a package that conflated
them would publish confident figures resting on absent data. When Alphabet does not tag proceeds
from equipment disposals, standardized free cash flow comes back as `—` rather than quietly
equalling the lease-adjusted figure.

A zero denominator is unresolved, not infinite and not zero. No invested capital means no return on
invested capital, which is a real answer.

## Assumptions

No model parameter is a literal in a function body. Each is a registry entry declaring its basis:

| basis | requires | confers |
|---|---|---|
| `filing_disclosure` | an accession and a quotable passage | ● reported |
| `derived_from_facts` | no fixed value; computed at runtime | ◆ derived |
| `published_third_party` | a citable URL | ▲ estimated |
| `user_input` | nothing; any stored value is illustrative | ○ scenario |

There is no basis for an author's unsupported judgement. An unsourced number can only enter as
`user_input`, and everything computed from it is visibly a scenario. A build fails on any numeric
literal in the modelling layer outside a short list of structural constants.

**A disclosed range is not a disclosed value.** Alphabet's 10-K says data centre and office
buildings are depreciated "over periods of seven to 40 years". The range is reported; where in it a
given building sits is not, so the range and any point estimate inside it are separate entries with
different bases. Lead time is treated the same way: the filing says the lag from purchase to service
"may extend from months to years" and declines to quantify it, so any specific number is the
reader's and marks its results accordingly.

## Definitions offered rather than settled

Where practice genuinely disagrees, the disagreement is exposed as separately named metrics. There
is no `roic()`; choosing between the definitions is the analyst's job, and the package's contribution
is making the choice visible.

**Free cash flow.** `fcf.reported` is cash from operations less purchases of property and equipment,
the definition most headlines use; it ignores finance leases and so understates capital intensity at
a filer that leases a meaningful share of its infrastructure. `fcf.lease_adjusted` subtracts
finance-lease principal, treating it as what it is: paying for capital assets. `fcf.standardized`
also adds back disposal proceeds, capturing net capital spending in full and departing furthest
from what companies print in their own releases.

**Invested capital.** `returns.invested_capital_operating` is total assets less current liabilities,
the simplest defensible basis; it includes the securities portfolio, which at a cash-rich filer
inflates the base and understates the return. `returns.invested_capital_ex_cash` removes cash and
marketable securities, at the cost of treating every dollar of securities as non-operating when some
is working capital. On Alphabet's fiscal 2025 figures the two bases differ by roughly seven
percentage points of return, which is the argument for naming both.

**Return on invested capital.** Point-in-time (`returns.roic`) understates returns for a company
whose capital grew during the period. Averaged (`returns.roic_average_capital`) is fairer during a
build-out. `returns.roic_rd_capitalized` treats research as the investment it economically is, which
requires an assumed useful life for research that no company discloses, so its results are scenarios.
`returns.incremental_roic` measures the return on capital *added*, which is usually far from the
average and is the noisiest figure here.

**Tax.** Returns use a supplied rate rather than the company's effective rate, which is distorted by
one-off items, foreign mix and share-based compensation in ways that have little to do with capital
productivity. The default is the US federal statutory rate, cited to 26 U.S.C. §11(b), and because
that is a third-party source rather than a company disclosure, every return computed from it is
marked estimated. A filer's marginal cash rate on incremental capital is not something its
published accounts reveal.

## Comparability

Headline capex is not comparable across filers without normalizing cash capex, accrued capex,
finance and operating leases, purchase commitments, asset mix, useful lives, fiscal calendars,
acquisitions and segment definitions. The package models fiscal periods per filer for this reason:
Microsoft's 2026Q2 and Alphabet's 2026Q2 cover different months, and treating the labels as
equivalent is wrong before any arithmetic happens.

Filers also migrate their XBRL tags. Alphabet reported revenue under
`RevenueFromContractWithCustomerExcludingAssessedTax` through the first quarter of 2025 and under
`Revenues` afterwards; reading either tag alone produces a history with a cliff in it that never
happened, so adapters stitch a canonical series across the tags a filer has used.

## The capital-vintage model

A vintage is capital spent at one moment, followed through the years in which it enters service,
earns and depreciates. Modelling it apart from the aggregate accounts keeps three timings distinct
that ordinary ratios collapse into one: cash leaves at the vintage year, capacity arrives after the
lead time, and depreciation begins when an asset is placed in service rather than when it was paid
for. That separation is why a build-out can crush free cash flow for years while the underlying
economics are unchanged, and it is what capex-over-revenue cannot show.

Depreciation is not a cash flow, but it shelters cash from tax, and during a build-out that shield
arrives years after the money went out. Tax is therefore computed on profit after depreciation.

**The engine runs backwards.** The forward question, what return this capital earns, needs inputs no
company discloses. The inverse question is answerable: given a stated claim, what utilization, margin,
revenue yield or delay would have to hold for it to be true? The output is a condition, and the reader
judges whether that condition is plausible.

When no value in the searched range satisfies a claim, the solver says so rather than producing a
number. The committed example demonstrates this: no utilization between 5% and 100% reaches a
three-year payback on those parameters, because the ramp rather than utilization is the binding
constraint. Reporting that the claim cannot hold anywhere in the range is the useful answer.

## Reconciliation

Facts are checked before anything is modelled. Assets equal liabilities plus equity at every reported
date; cumulative figures grow in magnitude within a fiscal year. A dataset failing these is not one
with a small error in it, it is one whose extraction is wrong somewhere, and every metric built on it
inherits the fault.

Skipped checks are reported separately from passed ones. A check that examined nothing is not
evidence of correctness.

## What the package will not do

- Rate a stock, set a price target, or make a recommendation.
- Publish a single definitive maintenance-capex number. It is not observable.
- Force an AI versus non-AI capex split. Most of the time "unallocated" is the honest category.
- Let generated prose introduce a number absent from the calculation graph.
- Cover Amazon or AWS. See [DISCLOSURE.md](DISCLOSURE.md).

## Limits worth knowing

Segment figures are absent. SEC Company Facts flattens away XBRL dimensions, so Google Cloud revenue
and operating income cannot be read from it even though Alphabet reports them; reaching them needs
the filing's XBRL instance. The adapter says so rather than returning an empty list that would read
as "this company has no segments".

Extraction covers an allow-list of concepts rather than sweeping everything, because a fact nobody
has classified onto a statement cannot be reconciled and would sit in the dataset unverified.

The same concept recurs across filings, sometimes with different values. The latest filing wins and
the disagreement is reported as a restatement rather than silently overwritten.
