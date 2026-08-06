# Methodology

This document is the reader-facing account of what the package computes and what it refuses to
compute. It fills in as each milestone lands; sections marked *not yet implemented* describe
committed design, not existing behaviour.

## Epistemic status

Every number carries one of five statuses, and calculations degrade to their weakest input.

| glyph | status | meaning |
|---|---|---|
| ● | reported | Stated by the company in a filing or release. |
| ◆ | derived | Computed deterministically from reported values alone. |
| ▲ | estimated | Depends on a judgement the company did not disclose. |
| ○ | scenario | Depends on a user-chosen assumption; a what-if, not a measurement. |
| ! | unresolved | Could not be determined from available evidence. |

Two consequences worth stating plainly. A calculation is never itself *reported*, however solid its
inputs — combining two disclosed figures produces a derived number, because the combination is the
analyst's choice. And a calculation touching anything undetermined comes out undetermined rather
than defaulting to zero, because a missing input and a zero input are different claims about the
world.

## Assumptions

No model parameter is a literal in a function body. Each is a registry entry declaring its basis:

- `filing_disclosure` — stated in a filing; requires an accession and a quotable passage.
- `derived_from_facts` — computed at runtime; pins no fixed value.
- `published_third_party` — from a citable non-company source; requires a URL.
- `user_input` — chosen by whoever runs the model; any stored value is illustrative only.

There is no basis for an author's unsupported judgement. That is not a rhetorical position: an
unsourced number can only enter as `user_input`, and everything computed from it is visibly a
scenario.

## Definitions offered, not settled

*Not yet implemented (M3).* Where practice genuinely disagrees, the package will offer named
alternatives rather than one blessed figure — several free-cash-flow definitions, conventional and
lease-adjusted and R&D-adjusted returns, and multiple maintenance-capex estimators. Comparing
companies on headline capex without normalizing for cash versus accrued capex, finance and operating
leases, purchase commitments, asset mix, useful lives, fiscal calendars, acquisitions and segment
definitions produces a number that looks meaningful and is not.

## The capital-vintage model

*Not yet implemented (M4).* Capital is split into economic asset classes, each with its own lead
time, useful life, utilization ramp and revenue yield, producing per-vintage service dates,
depreciation, capacity, cash flow and returns.

Its purpose is inverse. The package does not claim to know any company's internal returns; it answers
what utilization, pricing, margin, life and residual-value assumptions must hold for a management
claim to be true.

## What the package will not do

- Rate a stock, set a price target, or make a recommendation.
- Publish a single definitive maintenance-capex number.
- Force an AI versus non-AI capex split. Most of the time "unallocated" is the honest category.
- Let generated prose introduce a number absent from the calculation graph.
