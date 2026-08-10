# Changelog

Changes per release, most recent first. Dates are release dates.

## Unreleased

Two strands. An external review found seven P1 integrity defects, all of which
reproduced and two of which were producing wrong published numbers. Separately,
the Streamlit lab was rewritten to be readable.

### Fixed

- **The what-must-be-true solver answered wrongly in both directions.** It
  searched for the lever value where an error term crossed zero, which assumes
  the objective reaches the target continuously; payback steps. On the lab's
  default settings it reported that 67.3% utilization gives a three-year payback,
  where 67.3% gives five years and nothing in range gives three. It also refused
  achievable claims, because payback can jump from never to four years and skip
  five entirely. `required_for` now searches a monotone predicate, so the value it
  returns satisfies the claim by construction, and knows which direction each
  lever helps in. The committed example and the README both carried a false
  refusal: no utilization was said to reach a three-year payback, when 80.9% does.
- **Node ids collided on keyword order.** `subtract(a=x, b=y)` and
  `subtract(b=x, a=y)` produced one id for results of 7 and -7, because the
  kernel read `kwargs.values()`, which follows call-site order and carries no
  names. Arguments now bind through the signature. Every stored node id is
  unchanged, and pinned by a test.
- **Fractional asset lives were truncated.** A 5.5-year asset was written down to
  90.9% of cost; 5.9 years recovered less than 5.0; a life under a year meant the
  asset never entered service at all, silently. The final partial year is
  prorated. Fractional lead times are refused rather than rounded.
- **The audit could not detect tampering.** It checked that identifiers resolved,
  never that they agreed. An edited amount, unit, period or label passed, as did
  a value repointed at a different real node. Values are now compared with their
  calculations, and node ids re-derived from their inputs.
- **Failed reconciliation did not stop publication.** A trillion added to Assets
  gave fourteen failed identities, a published invested-capital figure a trillion
  out, and a clean audit. Failures are audit errors, and `analyze` refuses to
  write without `--allow-failed-reconciliation`.
- **Scenario assumptions were nominal.** Only the tuple's emptiness was checked,
  so a single blank string satisfied it, and the shipped example cited
  `useful_life.servers_and_network.googl`, which resolves in no registry -- with a
  test asserting that exact string. Ids must resolve, and bundles now carry the
  assumptions their scenarios name.
- **The SEC cache never refreshed.** The first download was served forever, with
  no age check and no way to ask for a new one. `--refresh`, `--max-age` and
  `--offline` on `ingest`, `analyze` and `reconcile`.
- **`reconcile` skipped the checks it advertised.** It passed canonical concept
  names to a matcher keyed on XBRL tags, so all twenty year-to-date checks
  matched nothing and were reported as skipped for want of data. Fourteen checks
  ran where thirty-four should have.
- **The simulator was off by a factor of a million.** It asked for spend in
  millions and handed the number to an engine that declares its outputs in USD, so
  a $10 billion program reported a net present value of `-162.21 USD`. It meant
  `-$162.2M`.
- Return on invested capital, capex intensity, IRR and three other metrics were
  declared `unit="ratio"` and rendered as bare decimals: `0.206971` rather than
  `20.70%`. The percent branch of `format_value` had never been reachable, and
  rounded to six places rather than the two `PERCENT_PLACES` specified.
- The Provenance page promised "the formula, the inputs and the filings beneath
  it" and rendered a single row, because the walk descended only into calculation
  nodes and every leaf is a fact. Lineage now bottoms out in the filings.
- Cumulative operating cash flow is not monotonic -- a cash-negative quarter
  reverses it legitimately -- so a decrease is reported as suspect rather than
  failing the report.
- An unavailable `--through` period names the periods that exist instead of
  raising `UnitMismatchError` about a metric's units.
- `use_container_width` is past its Streamlit removal date; charts pass
  `width="stretch"`.

### Added

- `AssetClassParameters` validates its economics. Negative spend produced a
  positive net present value; utilization above 100%, non-positive lives and
  margins above 1 all constructed.
- `CalculationNode.literal_inputs` records the bare arguments that went into a
  node id, so the id can be verified from the node.
- Property-based tests over the solver. Hypothesis was a declared dev dependency
  with no uses; the first two properties written found the step-discontinuity
  failure.
- Bundles reject a schema version they cannot read. Restatements keep concept,
  values and both accessions rather than a count.
- CI has a coverage floor, a 3.12/3.13 matrix, and a dependency audit.
- `format_compact` renders `$73.3B` where `format_value` renders
  `73,266,000,000.00 USD`. The SVG axis labeller shares it, so a tick and the card
  above it cannot disagree.
- `AtlasApplication.headline()`: capex and depreciation as reported facts.
  Alphabet's $91.4B of capital spending appeared on no page, and because every
  published value is a calculation the interface never showed a single ● figure.
- `FactScope.ANNUAL` keeps annual periods and balance-sheet dates, dropping
  quarters no chart plots.
- A timeline with fewer than three points renders as bars, so a thin bundle reads
  as sparse rather than broken.

### Changed

- The Overview leads with what the company spent, then groups the published
  values by the question they answer, rather than listing eleven in bundle order
  behind a bar chart counting the app's own figures.
- Requirement prose names its lever in words: `A utilization of 80.9% is required
  for payback of 3.0 years` rather than `utilization of 0.8086 is required for
  payback_years of 3`.
- The simulator's inputs sit in two columns with help text on each.
- The committed example is rebuilt with the annual scope.

## 0.2.0 — 2026-08-09

First release published to PyPI. The version skips 0.1.1 because the surface changed:
`UnsupportedEntityError` moved to `capex_atlas.adapters`, the adapter registry is now typed to the
`CompanyAdapter` protocol and adapters must implement `cumulative_concepts()`, `AtlasEvent` and the
`[xbrl]` extra are gone, and `duckdb` and `platformdirs` are no longer dependencies.

### Fixed

- `verify` never passed the fact scope to its rebuild, so any bundle written with
  `--facts used` or `--facts period` could never reproduce. The README documented exactly that
  sequence.
- `verify` reported a difference with nothing listed when the change sat outside the value diff. It
  now names the differing sections, and refuses a bundle it did not build rather than comparing
  different inputs.
- `reconcile` was registered twice and hardcoded the Alphabet adapter, which would have applied a
  December year-end to a June filer.

### Added

- Microsoft and Meta adapters, with cited useful-life entries from each 10-K and hash-pinned
  fixtures. Microsoft's June year-end exercises the fiscal calendar against real filings for the
  first time.
- Concept resolution moved behind the adapter, so a filer's tag vocabulary no longer leaks into
  shared code. Adding a company is now a new module and one registry entry.
- The cross-company symmetry check now constrains rather than returning early, and allows a
  filer-specific parameter only when that filer's own filing discloses it.
- Chart specifications are carried by bundles and rendered by both the app and a dependency-free,
  byte-deterministic SVG writer, which produces the committed README figures. The chart grammar had
  no caller in 0.1.0.
- `capex-atlas app` launches the lab, and the wheel ships it alongside a worked example, so
  `pip install "capex-atlas[app]"` works without a git checkout.
- `py.typed`, so downstream consumers get the annotations the package is already checked against.
- A tag-triggered release workflow using PyPI trusted publishing, which installs its own wheel into
  a clean environment before publishing.

### Removed

- `duckdb` and `platformdirs` runtime dependencies, and the `[xbrl]` extra. All three had zero
  import sites; the extra installed Arelle for a code path that does not exist.
- `AtlasEvent`, which had no caller and no test. It returns with the event log that needs it.
- An unreachable zero-flow guard in `payback_period`: at a crossing, `previous < 0` and
  `cumulative >= 0` force `flow > 0` strictly.

## 0.1.0 — 2026-08-06

First release. A deterministic engine that turns SEC filings into source-linked models of capital
deployment, with a reference application on top. No LLM code path: the agent layer is deliberately
deferred until the package can independently reproduce and reconcile reported numbers.

Coverage is Alphabet. Amazon and AWS are out of scope permanently; see `DISCLOSURE.md`.

### The two mechanisms

- Evidence status propagates automatically. Every value is reported, derived, estimated, scenario or
  unresolved, and every calculation degrades to its weakest input. A calculation is never itself
  reported; a missing input yields unresolved rather than zero.
- Assumptions carry citations or they do not exist. No model parameter may be a literal in a
  function body. There is no basis for unsupported judgement, so an uncited prior can only enter as
  user input and marks its results as what-ifs. Enforced by an AST scan of the modelling layer.

### Included

- SEC Company Facts ingestion, rate-limited, with an immutable hash-recorded raw store.
- Per-filer fiscal calendars, year-to-date to discrete-quarter derivation, and restatement detection.
- Alphabet adapter, including concept aliasing across the filer's XBRL tag migration.
- Reconciliation identities: balance sheet, cumulative-series monotonicity.
- Metric suite: three free-cash-flow definitions, capital intensity, and several named returns.
- Capital-vintage engine with an inverse "what must be true?" solver and tornado sensitivities.
- Analysis bundles: deterministic serialization, audit, diff, and byte-level reproducibility check.
- Streamlit reference lab and a Typer CLI.
- OpenTelemetry behind an optional extra, with an enforced metadata-only attribute policy.
- A worked example under `examples/`, rebuilt and audited in CI.

### Known limits

- Segment figures are unavailable from Company Facts, which drops XBRL dimensions. Reaching them
  needs the filing's XBRL instance via the `[xbrl]` extra.
- `returns.roic_rd_capitalized` takes a pre-computed research asset and amortization; the schedule
  that would produce them is not wired up.
- Microsoft, Meta and Oracle adapters are not written.
- Not published to PyPI.
