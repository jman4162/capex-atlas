# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

M0 (scaffolding) and M1 (schemas, provenance kernel, assumption registry) are built. Everything from
M2 on — SEC ingestion, adapters, metrics, the capital-vintage engine, bundles, the Streamlit app —
is a stub package with a docstring naming its milestone. The stubs exist so the import-linter
contracts cover each module from its first commit.

Implementation plan, including milestone sequencing and the conflict-of-interest reasoning:
`~/.claude/plans/please-create-an-implementation-sorted-donut.md`. The design conversation it came
from is `BACKGROUND_INFORMATION.local.md` (untracked; design input, not a spec to quote).

## Commands

```bash
uv sync --group dev
uv run ruff check . && uv run ruff format --check .
uv run mypy src/
uv run lint-imports                        # layer boundaries
uv run pytest                              # all
uv run pytest tests/governance -v          # citations and symmetry
uv run pytest tests/unit/test_metric.py -q # single file
uv run pytest -k "status_degrades"         # single test by name
```

If `capex_atlas` fails to import under `uv run`, the editable install is stale: fix with
`uv sync --group dev --reinstall-package capex-atlas`.

## What Capex Atlas is

An open-source Python package (`capex_atlas`) that turns public filings and earnings disclosures
into reproducible, source-linked models of hyperscaler capital deployment, cash flow, capacity
economics, and returns on invested capital. Target companies: AMZN, GOOGL, MSFT, META, ORCL.

It is deliberately **not** an "AI equity analyst." The governing boundary:

- **Python calculates.** All arithmetic lives in tested, callable metric functions.
- **Agents discover, classify, reconcile, challenge, and explain.** They never compute or overwrite
  a financial fact.
- **Every published number retains its formula, assumptions, and source evidence.**

The differentiator versus generic ratio libraries (FinanceToolkit et al.) is hyperscaler-specific
modeling: capital vintages, servers versus buildings, capacity lead times, depreciation lag,
backlog/RPO conversion, and AI-capex attribution.

## Layer architecture

One `capex_atlas` package with optional extras (`[xbrl]`, `[app]`, `[otel]`, and `[agents]` /
`[strands]` later), not the four-distribution monorepo the design doc sketches. The layer boundaries
that would have come from separate wheels are enforced instead by `import-linter` contracts in
`pyproject.toml`:

- `schemas` imports nothing else internal.
- `metrics`, `capital_vintages`, `scenarios` perform no I/O and no presentation.
- `provenance` and `assumptions` sit below the calculation layer.
- A whole-package layers contract, top to bottom: `cli` → `bundle` → `viz` → `scenarios` →
  `capital_vintages` → `metrics` → `accounting` → `adapters` → `normalization` → `xbrl` → `sources`
  → `provenance` → `assumptions` → `schemas`. (`obs` is deliberately outside the stack; tracing is
  callable from anywhere.)

Run `uv run lint-imports` after moving code between modules. Splitting into separate distributions
later is mechanical because these boundaries already hold.

Agent layers (`[agents]`, `[strands]`) land in v0.4, framework-neutral Protocols first.
`apps/streamlit` holds no analytical logic — pages call an `AtlasApplication` service layer.

Framework decisions and their rationale: Strands is an installable extra, never a hard dependency —
it is model-first, which is the wrong control model for accounting transformations. PydanticAI is
the alternative default for the agent layer. LangGraph only if persistent, resumable, human-in-loop
research sessions become necessary. Do not model ETL or accounting steps as agent nodes.

## Invariants that must not be violated

These are the substance of the project; code that breaks them is wrong even if it runs.

1. **Reported, derived, estimated, and scenario values never mix silently.** Every analytical value
   carries an `EvidenceStatus` in the data model, not just in UI styling
   (● Reported / ◆ Derived / ▲ Estimated / ○ Scenario / ! Unresolved).
2. **Agents never mutate reported facts.** They may propose mappings, extract claims, and draft
   prose. Mappings that change a financial calculation require human approval.
3. **No arithmetic in agent prose.** Any number in generated text must trace to a `CalculationNode`
   produced by a tested Python metric.
4. **Provenance is a first-class object,** not a footnote. Derived results are a graph of
   `CalculationNode`s (formula, inputs, assumptions, source refs, implementation version).
5. **Use `Decimal`, never binary floats,** for reported financial values.
6. **Management claims live in a separate claim ledger,** not in the financial fact table. Four
   distinct things: what was reported, what management said, what the model derives, what the
   analyst believes.
7. **No definitive single answer where the data cannot support one.** Do not publish one
   maintenance-capex number, one "correct" ROIC, or a forced AI/non-AI capex split — offer named
   alternative definitions/estimators and keep "unallocated" as an honest category.
8. **Never compare headline capex across companies without normalizing** cash capex, accrued capex,
   finance and operating leases, purchase commitments, asset mix, useful lives, fiscal calendars,
   acquisitions, and segment definitions.
9. **Never emit a stock rating.** The defensible output form is: "Under these disclosed facts and
   these explicit assumptions, the implied return range is X–Y%; the largest sensitivities are …"

## The two mechanisms (built; read these before touching the calculation layer)

**`@metric` in `provenance/metric.py`.** Metric bodies are plain `Decimal` arithmetic; the decorator
does everything else. Declare `metric_id`, `version`, `formula`, `unit` (or `INHERIT`), plus
`homogeneous_inputs=True` on anything additive and `allow_mixed_periods=True` only on genuinely
cross-period metrics like lagged incremental ROIC. The decorator unwraps `AnalyticalValue` and
`Assumption` inputs, checks units and periods, builds the `CalculationNode`, records it in the
active `calculation_graph()`, and returns an `AnalyticalValue`. Behaviour worth knowing:

- Output status is `weakest(DERIVED, *input statuses)` — a calculation is never `reported`.
- Any `None` input short-circuits to `UNRESOLVED` (override with `allow_missing_inputs=True`).
- `DivisionByZero` / `InvalidOperation` become `UNRESOLVED`, not a crash and not zero.
- Node ids are content-addressed, so identical work dedupes and a non-deterministic metric raises
  `GraphConflictError` instead of silently producing two answers.
- Never construct an `AnalyticalValue` with a hand-chosen status; that bypasses the kernel.

**The assumption registry** (`assumptions/`, data in `assumptions/data/*.toml`). No parameter may be
a literal in a function body. Basis determines status: `filing_disclosure` → reported (needs
accession + quotable passage), `derived_from_facts` → derived (pins no value),
`published_third_party` → estimated (needs URL), `user_input` → scenario. There is no `judgement`
basis, so an uncited prior can only enter as `user_input` and visibly marks results as what-ifs.
`tests/governance/` enforces this and cross-company symmetry; do not widen `ALLOWED_NUMBERS` in
`assumptions/audit.py` to sneak a constant past the scanner.

## Core domain objects

Built, in `schemas/`: `EvidenceStatus`, `FiscalPeriod` (typed, label round-trips via `parse`),
`SourceReference` (auto-derived id; `is_verifiable` means it names a passage), `FinancialFact`,
`AnalyticalValue`, `CalculationNode`, `ManagementClaim`, `ChartSpec`, `AtlasEvent`. All frozen.

Two id rules that look similar and are not: `FinancialFact.fact_id` is identity-only (entity,
concept, period, unit, dimensions) so the reconciliation layer can spot a restatement of the same
fact, while `AnalyticalValue.from_fact` folds the amount and source into its `value_id` so two
contradictory figures are distinct calculation inputs.

Not yet built: `CompanyAdapter` Protocol (M2), `AnalysisBundle` (M5 — deferred until scenarios and
validation results are real rather than half-specified).

## The capital-vintage model

The genuinely novel piece. Capex is split into economic asset classes (land, buildings, power,
cooling, servers, GPUs, CPUs, networking, storage, capitalized software, finance leases, CIP), each
with its own lead time, useful life, utilization ramp, and revenue yield. Per vintage it produces
service date, depreciation schedule, available capacity, NOPAT, IRR, payback.

Its purpose is inverse: not "what is the return," but **"what utilization, pricing, margin, life,
and residual-value assumptions must be true for management's claim to hold?"** Keep that framing in
API names, chart titles, and prose.

## Ingestion rules

- SEC Company Facts / submissions JSON APIs first; Arelle only when dimensions, extension
  taxonomies, or calculation relationships are needed.
- Raw artifacts are immutable, stored under `data/raw/<source>/<TICKER>/<period>/`, each with
  SHA-256, retrieval timestamp, source URL, accession number, form, fiscal period, document type,
  licensing status, and parser version.
- SEC downloader must set a descriptive user agent and rate-limit; default 2–3 req/s (well under
  SEC's historical 10/s limit).
- Do not commit or redistribute premium transcripts, consensus estimates, or proprietary pricing.
  License plan: Apache-2.0 for code, CC BY 4.0 for original educational text, separate manifest for
  source-document licenses.

## Observability

OTEL from the start, under a stable project namespace: `capex_atlas.source.*`, `.document.*`,
`.fact.*`, `.reconciliation.*`, `.metric.*`, `.scenario.*`, `.claim.*`, `.review.*`. Configure one
global tracer provider at the application level; do not let agents build their own.

**Metadata-only tracing by default.** Store IDs, accession numbers, tool/model names, token counts,
content hashes, character counts, schema names, confidence, validation status. Do not store full
prompts, filing text, transcripts, user data, or model reasoning content. GenAI semantic conventions
are still evolving — pin instrumentation versions, record the convention version, and normalize raw
spans into a versioned internal `CanonicalAgentTrace` before analysis. Keep high-cardinality
financial values out of span attributes; they belong in lineage records.

## Testing expectations

- Deterministic accounting checks on every filing: `Assets = Liabilities + Equity`, cash-flow
  reconciliation, segment-to-consolidated, quarter/YTD consistency.
- Golden filing fixtures for parser and adapter regression.
- Extraction evals against a hand-labeled dataset, scored on numeric, period, unit, evidence-span,
  concept-mapping, and reported-vs-estimated accuracy.
- Narrative grounding: reject generated claims with no supporting evidence, unsupported causal
  language, period or unit mismatches, guidance confused with actuals, or undisclosed "AI revenue"
  attribution.
- Adversarial cases the doc calls out: unrealized investment gains distorting net income, revised
  server useful lives, changed FCF definitions, capex including finance-lease principal,
  acquisition-inflated invested capital, concentrated RPO, 52/53-week fiscal years, XBRL extension
  tags replacing standard concepts.

## Streamlit app constraints

Pages call an `AtlasApplication` service layer and render presenters/components — no analytical
logic in page files, so the front end stays replaceable. Agent runs never trigger on a widget
rerun; they require an explicit `st.form` submission. Keep four privilege tiers distinct: explore
validated data (safe), run agent research (explicit, nondeterministic), approve extracted claims
(human), publish to shared dataset (privileged). Every view should export to static artifacts
(`analysis.atlas.json`, parquet tables, chart JSON, HTML/MD report).

## Build order

M0 scaffolding ✔ · M1 schemas + provenance + registry ✔ · M2 SEC ingestion + **Alphabet** adapter +
reconciliation · M3 metrics · M4 capital-vintage engine · M5 bundle + charts + CLI · M6 Streamlit +
OTEL · M7 publish v0.1. Then v0.2 Amazon adapter + claim ledger, v0.3 Microsoft and Meta, v0.4
agents.

**Alphabet is the first vertical slice, not Amazon** — a change from the design doc. The author works
at AWS, and the vintage engine infers exactly the quantities (utilization ramps, useful lives, lead
times) that job supplies private priors about. Building the methodology against a company he has no
relationship with, then applying it unchanged to Amazon, is the evidence that nothing was tuned
around inside knowledge. See `DISCLOSURE.md`. Do not reorder this without reading that file.

Build the deterministic pipeline before any agentic extraction — agents are only credible once the
package can independently reproduce and reconcile reported numbers.

## Positioning

Open-source on the author's personal GitHub (`jman4162/capex-atlas`), technical write-ups on
john-hodge.com/blog, with Summitward as a downstream consumer of selected outputs. Do not brand the
package as a Summitward product or name it "Summitward Capex Atlas."

## Prose conventions

`BACKGROUND_INFORMATION.local.md` is design input, not a spec to quote. When writing READMEs, docs,
docstrings, or commit messages, state results plainly and avoid AI-slop patterns (puffery,
significance-inflation, "delve/crucial/robust/seamless/leverage", rule-of-three padding). The
project's own credibility depends on precise, falsifiable wording about what is known versus
inferred.
