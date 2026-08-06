# Disclosure and analytical controls

## Disclosure

John Hodge, the author, works at Amazon Web Services. Capex Atlas is a personal project developed on
personal time and equipment, using only public sources: SEC filings, earnings releases,
presentations and public statements. It contains no confidential or non-public information about any
company.

The project is not affiliated with, endorsed by, or speaking on behalf of any company it analyzes.
Nothing it produces is investment advice. It emits no ratings, no price targets, and no
recommendations.

## Amazon and AWS are out of scope

Capex Atlas does not analyze Amazon or AWS, and will not. Coverage is Alphabet first, then Microsoft
and Meta, then Oracle.

This is stated plainly rather than handled by quietly leaving one company off the list, because a
gap a reader notices on their own invites worse explanations than the real one. The real one: an AWS
employee publishing models of their employer's capital returns is a conflict worth avoiding outright
rather than managing.

The exclusion has a cost, and it is worth naming. Amazon reports the most legible cloud segment of
the group and its management has given the most explicit account of the capital cycle, so the
package omits the clearest available teaching example. Readers who want that comparison will have to
build it themselves.

## Why the controls exist anyway

The obvious risk in a project like this is quoting something non-public. That is not the interesting
one. The capital-vintage engine infers utilization ramps, asset lives and capacity lead times, and
those are quantities anyone working in cloud infrastructure holds private views about. A default
like `utilization_ramp = [0.35, 0.60, 0.78, 0.85]` sitting unexplained in a function body would be
indistinguishable from an informed leak whether or not it was one, and no reader could tell.

Excluding Amazon does not fix that, because the same private priors would shape a model of anyone
else's infrastructure. The controls below are what make the provenance of every parameter checkable,
for every company equally, and they would be worth keeping even with no conflict in sight.

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

**3. No operational claims beyond the filings.** The project never asserts real server lifetimes,
utilization rates, failure rates, power efficiency or cost curves for any company, except as those
companies disclose them. Generated prose will be checked against the fact table by the
narrative-grounding evaluation; until that ships, it is a manual review step.

**4. Hygiene.** Personal GitHub, personal time and equipment, no employer branding or trademarks, no
trading on the basis of anything modelled here.

## For contributors

These controls apply to everyone, not just the author. A pull request that hardcodes a modelling
constant will fail CI regardless of who wrote it or how reasonable the number looks. If a parameter
genuinely cannot be cited, it belongs in the registry as `user_input`, with the resulting scenario
status shown to the reader. That is the honest treatment rather than a workaround.

Pull requests adding Amazon or AWS coverage will be declined. See above.
