# Changelog

Changes per release, most recent first. Dates are release dates.

## Unreleased

### Fixed

- The vintage simulator asked for spend in millions and handed the number to the engine unscaled,
  while the engine declares its outputs in USD. A $10 billion program reported a net present value
  of `-162.21 USD`; it meant `-$162.2M`. The form now takes billions and scales before the call,
  and a test pins the magnitude of the answer.
- Return on invested capital, capex intensity, IRR and the other three ratio metrics were declared
  `unit="ratio"` and rendered as bare decimals: `0.206971` rather than `20.70%`. They are now
  `unit="percent"`. The percent branch of `format_value` had never been reachable, and rounded to
  six places rather than the two `PERCENT_PLACES` specified, so both are fixed.
- The Provenance page promised "the formula, the inputs and the filings beneath it" and rendered a
  single row. `_walk` descended only into calculation nodes, and every leaf input is a fact stored
  separately in the bundle. Lineage now bottoms out in reported facts with their XBRL tag and
  period. An input the bundle no longer carries costs one row rather than the page.
- `use_container_width` is past its Streamlit removal date; charts now pass `width="stretch"`.

### Added

- `format_compact` renders `$73.3B` where `format_value` renders `73,266,000,000.00 USD`. Cards and
  axis labels use the compact form and keep the exact one in the tooltip. The SVG axis labeller
  delegates to the same helper, so a tick and the card above it cannot disagree.
- `AtlasApplication.headline()`: capex and depreciation as reported facts, with the two ratios built
  from them. Alphabet's $91.4B of capital spending appeared on no page, and because every published
  value is a calculation the interface never displayed a single ● reported figure.
- `FactScope.ANNUAL` keeps annual periods and balance-sheet dates, dropping quarters. The charts plot
  annual figures only, so `all` tripled the example for nothing drawn.
- A timeline with fewer than three points renders as bars. The example carried only the analyzed
  period, so the capital-deployment chart drew two specks in an empty frame.

### Changed

- The Overview leads with what the company spent, then groups the published values under what they
  answer, rather than listing all eleven in bundle order behind a bar chart counting the app's own
  figures. The evidence mix stays as a one-line caption.
- Requirement prose reads `A utilization of 67.3% is required for payback of 3.0 years` rather than
  `utilization of 0.6734 is required for payback_years of 3`.
- The simulator's inputs sit in two columns with help text on each.
- The committed example is rebuilt with the annual scope: 161 facts, 204 KB.

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
