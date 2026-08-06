# Capex Atlas

Turn public filings into reproducible, source-linked models of hyperscaler capital deployment,
cash flow, capacity economics, and returns on invested capital.

> **Status: pre-release (v0.1 in progress).** The schemas, provenance kernel and assumption registry
> are in place. Ingestion, metrics, the capital-vintage engine and the Streamlit app are not yet
> built. Nothing here produces analysis of a real company today.

## What it is

Existing libraries already compute broad sets of financial ratios. Capex Atlas is narrower and more
opinionated: it models the questions the AI build-out actually raises — capital vintages, servers
versus buildings, capacity lead times, depreciation lag, backlog conversion — and it refuses to
publish a number without the formula, the assumptions and the filing behind it.

The design boundary:

- **Python calculates.** Every number comes from a versioned, tested metric function.
- **Agents discover, classify, reconcile, challenge and explain.** They never compute or overwrite a
  financial fact. (Agent layer lands after the deterministic engine, not before.)
- **Every published number keeps its lineage.**

## The two mechanisms

Most of the package is ordinary data engineering. Two things carry the design.

**Evidence status propagates automatically.** Every value is `reported`, `derived`, `estimated`,
`scenario` or `unresolved`, and every calculation degrades to its weakest input:

```python
result = standardized_fcf(cfo, capex)  # both reported  -> ◆ derived
result = payback(capex, utilization_ramp)  # ramp is a user choice -> ○ scenario
```

A calculation is never itself "reported", however solid its inputs, and anything touching an
undetermined input comes out undetermined rather than quietly becoming zero. You cannot render a
figure without also knowing how much weight it carries.

**Assumptions carry citations or they do not exist.** No model parameter may be a literal in a
function body. Each is a registry entry with a declared basis:

| basis | requires | confers |
|---|---|---|
| `filing_disclosure` | accession + quotable passage | ● reported |
| `derived_from_facts` | no fixed value; computed at runtime | ◆ derived |
| `published_third_party` | a URL | ▲ estimated |
| `user_input` | nothing; the value is illustrative | ○ scenario |

There is deliberately no `judgement` basis. An unsourced prior can only enter as `user_input`, which
marks every downstream number as a what-if. A CI check walks the AST of the modelling layer and
fails the build on any uncited constant.

## Install

```bash
uv sync --group dev          # development
uv pip install capex-atlas   # not yet published
```

Optional extras: `[xbrl]` (Arelle), `[app]` (Streamlit + Plotly), `[otel]`.

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src/
uv run lint-imports     # layer boundaries
uv run pytest
```

`lint-imports` enforces the layering that would otherwise require splitting the project into
separate distributions: schemas depend on nothing internal, the calculation layer performs no I/O,
and nothing in `src/` imports the app.

## Scope and limits

The package does not, and will not, tell you whether to buy a stock. Public accounts cannot identify
a clean causal return on AI investment, so the honest output is conditional:

> Under these disclosed facts and these explicit assumptions, the implied return range is X–Y%.
> The largest sensitivities are utilization, pricing and useful life.

It likewise refuses to publish a single maintenance-capex figure, a single "correct" ROIC, or a
forced AI/non-AI capex split. Where the data supports several defensible definitions, it offers them
by name; where attribution is not disclosed, "unallocated" stays unallocated.

## Licensing

Code is Apache-2.0. Original documentation and diagrams are CC BY 4.0 (`LICENSE-docs`). Source
documents retain their own terms; the package bundles no proprietary market data, consensus
estimates or paywalled transcripts.

## Disclosure

The author works at Amazon Web Services. Capex Atlas is a personal project, built on personal time
and equipment, using only public filings and disclosures — no confidential or non-public
information. It is not affiliated with, endorsed by, or speaking for any company it analyzes.
Nothing here is investment advice, and the package emits no ratings or price targets.

Model parameters are citation-enforced and treatment is symmetric across companies by test, not by
assurance — see `DISCLOSURE.md` for how that is checked and why it is built this way.
