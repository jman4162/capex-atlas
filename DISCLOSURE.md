# Disclosure and conflict-of-interest controls

## Disclosure

John Hodge, the author, works at Amazon Web Services. Capex Atlas is a personal project developed on
personal time and equipment. It uses only public sources: SEC filings, earnings releases,
presentations and public statements. It contains no confidential or non-public information about any
company, including the author's employer.

The project is not affiliated with, endorsed by, or speaking on behalf of Amazon or any other
company it analyzes. Nothing it produces is investment advice. It emits no ratings, no price
targets, and no recommendations.

## Why this needs more than a disclaimer

The obvious risk — quoting something non-public — is not the real one. This package's capital-vintage
engine exists to infer utilization ramps, asset lives and capacity lead times. Those are exactly the
quantities someone working in cloud infrastructure would have private views about. A default like
`utilization_ramp = [0.35, 0.60, 0.78, 0.85]` sitting unexplained in a function body is
indistinguishable from an informed leak whether or not it is one, and no reader could tell the
difference.

Excluding Amazon from the analysis would not fix that. It would leave an AWS employee modelling the
unit economics of Azure and Google Cloud while conspicuously skipping AWS — a worse posture, and one
that makes the omission itself the story. The answer is to make the provenance of every parameter
checkable, for every company equally.

## Controls

**1. No uncited constants.** Every model parameter is a registry entry with a declared basis
(`filing_disclosure`, `derived_from_facts`, `published_third_party`, `user_input`) and a citation
where the basis demands one. There is no `judgement` basis. An unsourced prior can only enter as
`user_input`, which marks every number computed from it as a scenario.

Enforced by `tests/governance/test_no_uncited_constants.py`, which walks the AST of the modelling
layer and fails on numeric literals outside a short list of structural constants.

**2. Symmetric treatment.** Every company gets the same estimator set and the same parameter shapes.
Values differ; structure does not. Company-specific constants live only in adapters and must cite
that filer's accounting-policy disclosure.

Enforced by `tests/governance/test_registry_integrity.py`.

**3. Sequencing.** The methodology was built and applied to Alphabet first. The Amazon adapter comes
afterward, reusing a model that was fixed before it arrived — the strongest available evidence that
nothing was tuned around inside knowledge. The Amazon adapter gets a line-by-line citation audit at
review.

**4. No operational claims beyond the filings.** The project never asserts real server lifetimes,
utilization rates, failure rates, power efficiency or cost curves for any company, including AWS,
except as those companies disclose them. Generated prose will be checked against the fact table by
the narrative-grounding evaluation; until that ships, it is a manual review step.

**5. Employer clearance.** Outside-activity and open-source review with the employer precedes public
release of the Amazon-specific work.

**6. Hygiene.** Personal GitHub, personal time and equipment, no employer branding or trademarks, no
trading on the basis of anything modelled here.

## For contributors

These controls apply to everyone, not just the author. A pull request that hardcodes a modelling
constant will fail CI regardless of who wrote it or how reasonable the number looks. If a parameter
genuinely cannot be cited, it belongs in the registry as `user_input`, with the resulting scenario
status shown to the reader — that is the honest treatment, not a workaround.
