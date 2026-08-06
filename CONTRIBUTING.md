# Contributing

## Setup

```bash
uv sync --group dev
uv run pre-commit install
```

## Before opening a pull request

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src/
uv run lint-imports
uv run pytest
```

## Rules that CI enforces

These are not style preferences. A change that breaks one of them will fail the build.

**No uncited constants in the modelling layer.** Every parameter belongs in the assumption registry
with a declared basis and, where the basis requires it, a citation a reader can check. If you cannot
cite a value, register it as `user_input`. That is the honest treatment, and it correctly marks
downstream results as scenarios. Do not widen `ALLOWED_NUMBERS` in `assumptions/audit.py` to get a
number past the check.

**Symmetric treatment across companies.** Every filer gets the same estimator set and parameter
shapes. Values differ; structure does not. Company-specific constants live in adapters and cite that
filer's accounting-policy note.

**Layer boundaries.** `lint-imports` enforces them. Schemas import nothing internal; the calculation
layer performs no I/O; nothing in `src/` imports the app.

**Arithmetic lives in metrics.** Numbers reaching a chart, report or CLI come from a `@metric`
function with a formula string, a version and tests. A metric whose formula changes gets a version
bump so historical bundles keep reproducing their original values.

**Evidence status is never asserted by hand.** It propagates from inputs. If you find yourself
constructing an `AnalyticalValue` with a status you chose, you are probably bypassing the kernel.

## Adding a company adapter

1. Vendor golden fixtures from EDGAR (public domain) with hashes; tests must not hit the network.
2. Cite every accounting-policy constant to a specific note in that company's filing.
3. Confirm the reconciliation identities pass before adding metrics.
4. Check the parameter shape matches the existing adapters; the symmetry test will tell you.

## Scope

Out of bounds, by design: stock ratings, price targets, a single "correct" ROIC, a definitive
maintenance-capex number, and any forced AI/non-AI capex split. Where public data cannot settle a
question, the package says so rather than picking an answer.
