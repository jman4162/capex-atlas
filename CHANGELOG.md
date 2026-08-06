# Changelog

Changes per release, most recent first. Dates are release dates.

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
