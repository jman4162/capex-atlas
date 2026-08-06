# Capex Atlas

Turn public filings into reproducible, source-linked models of hyperscaler capital deployment,
cash flow, capacity economics, and returns on invested capital.

> **Status: pre-release (v0.1 in progress).** The engine, the CLI and the reference app are working
> end to end for Alphabet. Documentation, a published example bundle and a hosted demo are not done.

> **Not advice.** Capex Atlas is educational software. It is **not investment, legal, tax or
> accounting advice**, carries **no warranty of accuracy or completeness**, and its authors accept
> **no liability** for any loss arising from its use. It publishes no ratings, price targets or
> recommendations. Verify every figure against the filings it cites. Read
> [DISCLAIMER.md](DISCLAIMER.md) before relying on anything here.

## What it is

Existing libraries already compute broad sets of financial ratios. Capex Atlas is narrower and more
opinionated. It models the questions the AI build-out actually raises (capital vintages, servers
versus buildings, capacity lead times, depreciation lag, backlog conversion), and it refuses to
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
undetermined input comes out undetermined rather than silently collapsing to zero. You cannot render a
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
./scripts/slopcheck.sh          # prose: slopscore + slopless
./scripts/slopcheck.sh score    # slopscore only, no Node needed
```

Build an analysis and browse it:

```bash
export CAPEX_ATLAS_SEC_USER_AGENT="you (you@example.com)"   # SEC asks who is calling
uv run capex-atlas analyze GOOGL --through 2025FY -o examples/googl-2025fy
uv run capex-atlas audit examples/googl-2025fy    # every value must trace to evidence
uv run streamlit run apps/streamlit/app.py -- --bundle examples/googl-2025fy
```

`lint-imports` enforces the layering that would otherwise require splitting the project into
separate distributions: schemas depend on nothing internal, the calculation layer performs no I/O,
and nothing in `src/` imports the app.

## Coverage

Alphabet first, then Microsoft and Meta, then Oracle. Amazon and AWS are out of scope, stated up
front rather than left as a gap for readers to interpret: the author works at AWS, and publishing
models of an employer's capital returns is a conflict better avoided than managed. `DISCLOSURE.md`
gives the full reasoning, including what the exclusion costs.

## Scope and limits

The package does not, and will not, tell you whether to buy a stock. Public accounts cannot identify
a clean causal return on AI investment, so the honest output is conditional:

> Under these disclosed facts and these explicit assumptions, the implied return range is X to Y percent.
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
and equipment, using only public filings and disclosures, with no confidential or non-public
information. It is not affiliated with, endorsed by, or speaking for any company it analyzes.
Nothing here is investment advice, and the package emits no ratings or price targets. Amazon and AWS
are excluded from coverage entirely.

Model parameters are citation-enforced and treatment across companies is symmetric by test rather
than by assurance. `DISCLOSURE.md` covers how that is checked and why it is built this way.
