# System Structure

## Role

This file is the current source of truth for the repository and module structure of the system.

Current local repository folder name: `sec_insight_rag`.

Keep this file updated whenever:

- a top-level folder or important file is added, removed, or renamed
- a `src/` module responsibility changes
- a planned module becomes implemented
- generated storage locations change
- important local verification workflows change

Use `proposal.md` for the product goal, architecture direction, MVP scope, and milestones. Use this file for the most updated structure of the actual system. If `proposal.md` and this file disagree about current folders or module responsibilities, this file should be updated to reflect the actual repository structure.

Completed root `plan*.txt` milestone notes are local-only historical context.
Use Git history for past reasoning, not as current structure truth.

## Visual Overview

### Current Implemented Flow

```text
main.py
  |
  v
src/ingestion/company.py
  |
  +-- src/ingestion/tickers.py        -> resolve ticker to CIK
  +-- src/ingestion/submissions.py    -> fetch SEC submissions
  +-- src/ingestion/companyfacts.py   -> fetch SEC XBRL companyfacts
  +-- src/ingestion/filings.py        -> list and download active-window 10-K and 10-Q filing HTML
  +-- src/ingestion/inline_xbrl.py    -> load active Inline XBRL and extension taxonomies with Arelle
  +-- src/processing/xbrl_normalizer.py
  |     -> normalize companyfacts into NormalizedFact records
  +-- src/processing/inline_xbrl.py
  |     -> normalize issuer-extension and dimensional Arelle facts
  +-- src/processing/mapping_targets.py
  |     -> build canonical metric target coverage helpers
  +-- src/processing/active_window.py
  |     -> select latest 5 annual and latest 12 quarterly active periods
  +-- src/processing/base_metrics.py
  |     -> map clean raw facts into business-friendly base metrics
  +-- src/analyze/industry_classification.py
  |     -> assign company hard-industry labels from 10-K Item 1 Business with Gemini
  +-- src/indicators/engine.py
  |     -> calculate deterministic derived indicators from active base metrics
  |
  +-- src/storage/facts_repository.py
  |     -> preserve source-separated raw observations and duplicate evidence in SQLite
  +-- src/storage/company_repository.py
  |     -> persist company registry and refresh state
  +-- src/storage/industry_labels_repository.py
  |     -> persist reusable company hard-industry labels and evidence
  +-- src/storage/concept_mappings_repository.py
  |     -> persist approved learned mappings used by hard mapping
  +-- src/storage/filings_repository.py
  |     -> persist filing inventory and active-window state
  +-- src/storage/metrics_repository.py
  |     -> persist mapped base financial metrics
  +-- src/storage/indicators_repository.py
        -> persist derived financial indicators and skipped calculations

Plan 203 accession evidence adapter (implemented, not yet wired into
`ingest_company`):

src/ingestion/arelle_inventory.py
  |
  +-- verify a per-accession result cache and process misses sequentially
  +-- src/ingestion/arelle_worker.py
  |     -> spawn one fresh child process and one Arelle Session per accession
  +-- src/processing/arelle_extraction.py
  |     -> extract facts, taxonomy metadata, relationships, validations, and diagnostics
  +-- src/processing/arelle_evidence.py
        -> return an immutable, canonical JSON `complete` or `failed` result

experiments/MS5/milestone5_retrieval_pipeline.py
  |
  v
src/retrieval/service.py
  |
  +-- src/storage/filings_repository.py
  |     -> load active-window filing records and source paths
  +-- src/retrieval/parser.py
  |     -> extract visible, form-aware filing sections
  +-- src/storage/retrieval_repository.py
        -> persist canonical chunks and current index generation state

Generated local data:

data_store/filings/          downloaded SEC filing HTML
data_store/knowledge/        local formula proposal cache and versioned retrieval indexes
stock_data.db                SQLite database
  raw_xbrl_facts             source-separated XBRL observations with compact duplicate evidence
  companies                  local company registry
  company_industry_labels    reusable hard-industry labels and assignment evidence
  filings                    ingested filing inventory
  xbrl_concept_mappings      governed approved learned mappings
  financial_metrics          base metrics mapped from raw XBRL facts
  financial_indicators       derived indicators with formulas and traceability
  filing_chunks              canonical section-aware filing text chunks
  retrieval_index_state      current complete retrieval generation per company
```

### Backend Layer Map

```text
User entrypoints
  |
  +-- main.py                 local CLI-style ingestion report
  +-- src/api/                FastAPI routes
  |
  v
Application workflow
  |
  +-- current: src/ingestion/company.py
  +-- planned: src/workflows/
  |
  v
Data and analysis layers
  |
  +-- src/ingestion/          SEC API access and filing downloads
  +-- src/processing/         XBRL normalization, fact cleanup, active-window selection,
  |                            and deterministic base metric mapping
  +-- src/storage/            SQLite persistence and retrieval for raw facts,
  |                            companies, filings, metrics, indicators, and chunks
  +-- src/indicators/         deterministic derived financial indicators
  +-- src/retrieval/          local filing chunking, hybrid indexing, and evidence retrieval
  +-- src/analyze/            planned Gemini/RAG answer synthesis
```

### Evidence Flow Goal

```text
SEC companyfacts + active filing Inline XBRL
  |
  v
Reported XBRL facts
  |
  v
Base financial metrics
  |
  v
Derived indicators
  |
  v
Deterministic financial analysis --------+
                                          |
SEC filing HTML                           |
  |                                       |
  v                                       v
Section-aware chunks -> retrieval evidence
  |                                       |
  +-------------------+-------------------+
                      v
             Grounded LLM explanation
```

The important rule is that each box should remain traceable. Reported facts, calculated indicators, deterministic analysis, filing evidence, and LLM interpretations should not be blended together without labels.

## Current Top-Level Structure

```text
.
  .gitignore
  CONTEXT.md
  README.md
  agents.md
  config.env
  discussion.txt
  main.py
  proposal.md
  pyproject.toml
  uv.lock
  data/
  data_store/
  docs/
  experiments/
  src/
  tests/
```

## Top-Level Responsibilities

- `.gitignore`: Git ignore rules.
- `CONTEXT.md`: Domain glossary for canonical financial-evidence terminology. It does not contain implementation or architecture decisions.
- `README.md`: Local setup and run notes.
- `agents.md`: Project instructions for coding agents.
- `config.env`: Local configuration and secrets. Do not treat as public documentation.
- `discussion.txt`: Architecture discussion, follow-up questions, and decision notes.
- `experiments/`: Milestone experiment folders, local experiment proposals, runnable experiment scripts, and shared generated experiment storage. Explicit milestone experiment designs live in each `experiments/MS*/experiment_proposal.md` file.
- `main.py`: Local CLI-style script that runs company ingestion and prints a SEC/XBRL ingestion report.
- `proposal.md`: Current product scope, architecture direction, and MVP roadmap.
- `pyproject.toml`: Python project metadata and dependencies.
- `tests/`: Automated pytest coverage for implemented deterministic behavior and important failure paths.
- `uv.lock`: Locked dependency versions for `uv`.
- `stock_data.db`: Local generated SQLite database. This is runtime data, not source architecture.

## Data And Storage

```text
data/
  exports/
  fixtures/

data_store/
  filings/
  knowledge/
```

- `data/fixtures/`: Saved SEC API responses and sample data. The `arelle/`
  subfolder contains a minimal local XBRL instance and taxonomy used to verify
  the isolated Plan 203 adapter without SEC network access. Treat fixtures as
  immutable inputs.
- `data/exports/`: Generated CSV export location.
- `data_store/filings/`: Downloaded SEC filing documents.
- `data_store/knowledge/formula_proposals/`: Generated exact-context cache for report-only LLM formula proposal decisions. It stores structured successful formula, zero-target, or `no_formula` decisions, not recovered metrics.

## Documentation

```text
docs/
  experiments.md
  mapping_policy.md
  structure.md
```

- `docs/experiments.md`: Central experiment runbook and index. It defines shared experiment rules, data modes, folder naming, and links to per-milestone proposal files.
- `docs/mapping_policy.md`: Mapping governance policy for broad raw XBRL ingestion, explicit hard industry label assignment, selective base metric mapping, target raw fact coverage, and unknown concept review.
- `docs/structure.md`: Current repository and module structure. This file should stay synchronized with the actual code layout.

## Experiment Proposals

```text
experiments/
  storage/
  MS1/
    experiment_proposal.md
  MS2/
    experiment_proposal.md
    milestone2_ingestion_showcase.py
  MS2_5/
    experiment_proposal.md
    milestone25_live_sec_inspection.py
  MS3/
    experiment_proposal.md
    milestone3_indicator_engine.py
  MS4/
    experiment_proposal.md
  MS5/
    experiment_proposal.md
    milestone5_retrieval_pipeline.py
  MS6/
    experiment_proposal.md
  MS7/
    experiment_proposal.md
```

- `experiments/MS1/experiment_proposal.md`: Human-inspection proposal for the Milestone 1 scaffold experiment. It defines the local project structure, settings, and API health output to inspect.
- `experiments/MS2/experiment_proposal.md`: Human-inspection proposal for the Milestone 2 SEC/XBRL ingestion and normalization experiment. It defines input cases, intended terminal output, artifacts to inspect, edge cases, and expected outcomes.
- `experiments/MS2/milestone2_ingestion_showcase.py`: Runnable Milestone 2 experiment script that prints the SEC/XBRL ingestion and normalization showcase described by the Milestone 2 proposal.
- `experiments/storage/`: Generated shared experiment storage. Current MS2.5 live runs use `experiments/storage/experiment.db` and `experiments/storage/filings/` so later milestone experiments can inspect the same isolated state without touching `stock_data.db`.
- `experiments/MS2_5/experiment_proposal.md`: Human-inspection proposal for the Milestone 2.5 ingestion and mapping examination harness. It covers persistent isolated storage, update checks, active-window evidence, persisted industry labels, target and raw-fact coverage, Inline XBRL extensions, approved learned mappings, report-only LLM formula proposal diagnostics, unknown/alternate tags, financial metric lineage, saved reports, and SQLite/CSV evidence.
- `experiments/MS2_5/milestone25_live_sec_inspection.py`: Runnable Milestone 2.5 experiment script that saves `experiments/MS2_5/milestone25_mapping_report_<TICKER>.md` without printing the report body, then prints a one-line report generation duration and saved report path. The compact report contains section 0 summary, section 0A selected XBRL concept counts by period, section 1 mapped/missing target status, section 2 detailed formula and provider-outcome evidence split into 10-K and 10-Q subsections, and section 3 one deterministic summary recommendation per selected missing target-period. Section 2 keeps identical displayed formulas grouped while showing exact period coverage for each provider. Section 3 reports `formula` for a two-of-three matching validated component signature, `zero` for two-of-three validated zero-evidence outcomes, and `review_required` otherwise; disabled runs, empty eligible fact pools, and targets without contexts remain visible. Formula calls use the ordered `gpt-5-mini`, `gemini-3.1-flash-lite`, and `gemini-2.5-flash` panel over the existing target-compatible context and batching flow. Terminal progress distinguishes total model outcomes and provider-context slots from reused outcomes and numbered live batch requests, so a fully cached model remains visible without making another API call. The script preserves report-only behavior, exact per-model cache separation, active 10-K/10-Q filtering, primary monetary-unit selection, compact period labels, taxonomy-prefix stripping, concise terminal progress, `--no-formula-proposals`, compatibility flags, `experiments/storage/experiment.db`, filing downloads, supporting CSV exports, and the configurable formula cache directory.
- `experiments/MS3/experiment_proposal.md`: Human-inspection proposal for the Milestone 3 indicator engine experiment. It defines active accession-window scope, yearly and quarterly indicator tables for the requested catalog, skipped-period reasons, formulas, and source-metric traceability output.
- `experiments/MS3/milestone3_indicator_engine.py`: Runnable Milestone 3 experiment script that reads stored `financial_indicators` and writes a `.txt` report under `experiments/MS3` with active accession-window scope, yearly and quarterly indicator tables for the requested ticker or tickers, skipped reasons, formulas, and source traceability.
- `experiments/MS4/experiment_proposal.md`: Human-inspection proposal for the Milestone 4 deterministic financial analytics experiment. It defines trend, comparison, gap, outlier, and chart-ready output.
- `experiments/MS5/experiment_proposal.md`: Human-inspection proposal for the Milestone 5 retrieval pipeline experiment. It defines active filing coverage, section-aware chunking, generation state, hybrid retrieval metadata, source lineage, and saved text-report output.
- `experiments/MS5/milestone5_retrieval_pipeline.py`: Runnable local retrieval experiment that builds or reuses a company index, accepts repeatable queries, saves `experiment_report_<TICKER>.txt`, and prints only a brief terminal summary by default. The saved report labels retrieval synchronization duration, initial cold-query duration, subsequent warm-query durations, active filing count, chunk count, embedding model, chunk settings, and whether the embedding cache existed before sync.
- `experiments/MS6/experiment_proposal.md`: Human-inspection proposal for the Milestone 6 Gemini integration experiment. It defines model, prompt-source, prompt-preview, and call-metadata output.
- `experiments/MS7/experiment_proposal.md`: Human-inspection proposal for the Milestone 7 RAG analysis experiment. It defines evidence inventory, answer section separation, references, and unsupported-claim checks.

Runnable experiment scripts should live inside the same milestone folder as
their proposal when implemented.

## Source Modules

```text
src/
  __init__.py
  analyze/
  api/
  config/
  indicators/
  ingestion/
  processing/
  retrieval/
  storage/
```

### `src/config/`

Runtime configuration loading.

Current files:

- `settings.py`: Defines `Settings`, chat-model validation, local retrieval model/chunk settings, storage paths, and `load_settings`.
- `__init__.py`: Exports configuration helpers.

Key responsibilities:

- Load `config.env`.
- Normalize local environment values.
- Keep the default LLM model pinned to `gemini-2.5-flash`.
- Expose storage paths and SEC/Gemini configuration.

### `src/api/`

FastAPI application entrypoint.

Current files:

- `main.py`: Defines `create_app`, creates the FastAPI app, loads settings, and exposes `GET /health`.
- `__init__.py`: Package marker.

Key responsibilities:

- Own HTTP route definitions.
- Keep route logic thin.
- Call workflows or service modules rather than duplicating ingestion, storage, analytics, retrieval, or LLM logic.

### `src/ingestion/`

SEC-facing ingestion logic and current company-level ingestion orchestration.

Current files:

- `sec_client.py`: SEC HTTP client behavior.
- `tickers.py`: SEC ticker mapping and ticker-to-CIK resolution.
- `submissions.py`: SEC submissions retrieval plus complete recent-and-archived
  annual Inline XBRL inventory discovery for Plan 203.
- `companyfacts.py`: SEC companyfacts URL building and retrieval.
- `inline_xbrl.py`: Arelle-backed loading of active SEC Inline XBRL documents and extension taxonomy dependencies.
- `arelle_inventory.py`: Plan 203 sequential annual-inventory runner. It
  verifies filing identity, entry-point and dependency hashes, Arelle and result
  versions, and canonical payload hashes before reusing an exact per-accession
  result; cache misses run through the isolated worker one at a time. Complete
  and failed results remain explicit, while corrupt, changed, or incompatible
  cache entries are regenerated. A sibling versioned input manifest records
  the accession directory plus caller-declared external local dependency paths
  and hashes and binds them to the result payload hash, so dependency repairs
  and interrupted cache publication cannot reuse a failed result produced from
  different inputs.
- `arelle_worker.py`: Plan 203 accession boundary that starts a fresh spawned
  child process, creates one Arelle Session, loads and validates one local entry
  point, closes the session, and returns only canonical project-owned JSON.
- `filings.py`: Filing metadata listing, latest-form selection helpers, and filing document download.
- `refresh_policy.py`: Next-check date heuristics for 10-K and 10-Q refresh checks, plus business-day helpers.
- `company.py`: Refresh-aware `ingest_company` orchestration and `CompanyIngestionResult`.
- `company.py`: also exposes `delete_ingested_company` for local company reset/delete orchestration, including canonical retrieval rows and generated index artifacts.
- `errors.py`: SEC ingestion error types.
- `__init__.py`: Public exports for ingestion APIs.

Key responsibilities:

- Resolve ticker symbols to CIKs.
- Retrieve SEC submissions and companyfacts JSON.
- Discover all Inline XBRL `10-K` and `10-K/A` accessions by traversing recent
  submissions and every referenced history file, without changing the legacy
  active-window company workflow yet.
- Load active Inline XBRL filings when deterministic target coverage remains incomplete.
- Produce an additive Plan 203 evidence result for one locally acquired
  accession with explicit `complete` or `failed` status. This seam is not yet
  connected to the legacy company ingestion workflow or
  `get_inline_xbrl_facts()`.
- Process an ordered set of already acquired annual accession requests
  sequentially and reuse unchanged results from a caller-selected local cache.
  Failed results with a verified entry-point hash remain visible and reusable
  only while the versioned local-input manifest is also unchanged, preventing
  automatic retry loops without hiding repaired dependencies.
- Backfill Inline XBRL enrichment once for previously ingested companies whose active local filing artifacts predate the adaptive mapping layer.
- Check local company registry state before live SEC ingestion.
- Reuse local company data when refresh is not due.
- Check SEC submissions when refresh is due and preserve local data if the refresh fails.
- Select active-window 10-K and 10-Q filings from the latest 5 annual and latest 12 quarterly fact periods.
- Download missing active-window filing documents and reuse already downloaded filing documents.
- Use Gemini with 10-K Item 1 Business to assign reusable hard-industry labels when a Gemini key is configured, keeping only supported high-confidence labels and falling back to existing or source-controlled labels when classification is unavailable, invalid, or low confidence.
- Delete inactive downloaded filing evidence while preserving filing metadata and raw XBRL facts.
- Coordinate current company ingestion by calling processing and storage modules.
- Coordinate local company deletion by calling storage repositories and guarded filing cleanup.
- Calculate heuristic next-check dates for annual and quarterly filing refreshes.

Boundary rule:

- SEC request logic belongs here.
- XBRL normalization logic belongs in `src/processing/`.
- SQLite persistence logic belongs in `src/storage/`.
- Long-term user-facing orchestration may move to `src/workflows/` when that module exists.

### `src/processing/`

Companyfacts and Inline XBRL normalization, active-window selection,
canonical target coverage helpers, deterministic base metric mapping, and
metric-first formula/zero evidence resolution for mapping review.

Current files:

- `xbrl_normalizer.py`: Defines `NormalizedFact`, `normalize_companyfacts`, `normalize_fact_entry`, and duplicate fact marking.
- `inline_xbrl.py`: Converts Arelle filing models into normalized issuer-extension and dimensional raw facts without fetching SEC data or writing storage.
- `arelle_evidence.py`: Immutable request, filing, fact, concept, context, unit,
  relationship, formula assertion, diagnostic, namespace, source-document,
  count, timing, and result records plus canonical JSON encoding and payload
  verification for the Plan 203 adapter. Source-document records retain both
  the source URI and resolved local path so dependency hashes can be rechecked.
- `arelle_extraction.py`: Extracts project-owned facts, concept metadata,
  presentation, calculation, definition, label, reference and formula
  relationships, formula assertion counts, scoped validation diagnostics,
  namespaces, source documents, hashes, and counts from a live Arelle model
  inside the child process.
- `observation_reconciliation.py`: Reconciles separately persisted Arelle and
  Company Facts rows within one selected accession. It records matches,
  conflicts, source-only supplements, blocked-fact replacements, and ambiguity
  quarantine; selects only usable numeric observations; preserves source rows,
  diagnostics, field-level metadata attribution, semantic fact identity, and
  the complete Arelle structural result for later precedence and mapping.
- `accession_precedence.py`: Resolves reconciled annual accessions independently
  per semantic fact identity, statement-network identity, and concept metadata
  field. It preserves valid earlier facts and networks through partial or
  invalid amendments, retains duplicate/conflict lineage, and exposes an exact
  accounting-context gate for mixed-accession formula components.
- `mapping_targets.py`: Builds canonical target definitions and missing-target checks for hard-mapping coverage.
- `formula_proposals.py`: Builds target-unit-compatible, statement-bucketed raw fact contexts for report-only LLM formula proposals, keeps only the primary monetary unit per filing period for monetary targets while preserving all raw units in storage/export evidence, collapses identical period raw-concept pools into one provider context with period coverage, computes exact reusable formula context fingerprints and statement-scoped batch keys, normalizes single-target and batch provider responses, caches successful structured formula, zero-target, or no-formula decisions per target/context/provider, and deterministically validates formula components or cited zero-evidence facts against representative raw XBRL facts. Formula validation distinguishes actual fact dates inside comparative filings, prefers an undimensioned fact when dimensional variants coexist for the same concept/date, and still rejects truly ambiguous same-date duplicates.
- `metric_coverage.py`: Collapses tag-level target coverage and formula/zero diagnostics into one metric-level review surface. It does not approve mappings, persist recovered values, or feed indicators.
- `active_window.py`: Selects the active analysis window: latest 5 fiscal years of 10-K data and latest 12 quarters of 10-Q data.
- `base_metrics.py`: Maps clean supported raw XBRL facts into business-friendly base metric records using catalog-backed approved mapping candidates.
- `metric_recovery.py`: Produces report-only recovery diagnostics for missing debt metrics from existing mapped base metric components; it does not persist recovered values or feed indicators.
- `company_industry_labels.py`: Hard industry label definitions, source-controlled fallback assignments for experiment tickers, and review placeholders for unassigned companies.
- `mapping_catalog.py`: Inspectable common base and hard-industry target raw fact catalog plus approved raw concept to internal metric candidates.
- `concepts.py`: Supported concepts, taxonomies, and forms.
- `periods.py`: SEC date parsing and period classification helpers.
- `quality.py`: Quality flag constants and helpers.
- `errors.py`: XBRL processing error types.
- `__init__.py`: Public exports for processing APIs.

Key responsibilities:

- Normalize SEC companyfacts into auditable fact records.
- Normalize Inline XBRL issuer-extension and dimensional facts supplied by the ingestion layer.
- Support broad raw-archive normalization across all requested forms, taxonomies, and concepts.
- Keep the common supported `us-gaap` concept list for selective metric mapping and reporting, not as the raw archive limit.
- Keep hard industry label definitions and fallback assignments auditable; use SIC and observed concepts as supporting evidence for review, while Gemini classification from 10-K Item 1 Business owns automated label inference when configured.
- Compare hard-industry target raw facts against observed raw facts and mapped financial metrics for experiment report coverage.
- Preserve raw values separately from parsed numeric values.
- Keep live Arelle objects inside their child process and preserve warnings or
  errors on the affected fact or relationship evidence when Arelle supplies an
  object reference.
- Normalize CIK, taxonomy, concept, unit, periods, fiscal year/period, form, filing date, accession number, frame, and source metadata.
- Preserve namespace URI, context ID, dimensions, consolidation state, concept balance, numeric type, and source document for Inline XBRL facts.
- Reconcile Arelle and Company Facts observations within an accession without
  merging source rows or applying the later cross-accession precedence policy.
- Build the mapping fact view with latest-valid-accession precedence while
  retaining invalid, quarantined, equivalent, and superseded source history;
  apply amendment precedence separately to facts, statement networks, and
  concept metadata fields.
- Resolve coverage at the internal-metric level before human or LLM review:
  mapped metrics need no action, approved alternate concepts count as covered,
  and unresolved metrics expose formula-from-raw-concepts, zero-target, or
  no-evidence review evidence.
- Validate report-only LLM formula proposals for all unresolved targets against
  period-scoped raw XBRL fact pools, including found target facts, mapped
  metrics, approved alternates, and unknown/unmapped facts. The MS2.5 report
  sends active target-unit-compatible contexts to the provider panel, suppresses
  secondary monetary currencies from provider contexts when a filing period has
  a primary monetary unit, reuses exact provider results when the target/model/raw-concept pool is identical
  across periods, batches uncached provider calls only within the same target
  statement group and compatible raw-concept context, keeps the full eligible
  fact pool visible as evidence, and shows target primary statement, period
  context, cache status, provider output, component or zero-evidence facts, and
  deterministic validation status.
- Produce report-only debt recovery diagnostics for missing `debt_current` and
  `debt_noncurrent` from already mapped component metrics, while keeping
  recovered values out of `financial_metrics` and indicators.
- Add quality flags for missing, malformed, unsupported, duplicate, or ambiguous facts.
- Select the default active analysis window without deleting the raw XBRL archive.
- Map clean supported base metric concepts such as revenue, total assets, net income, and operating cash flow into base metric records.

Boundary rule:

- Do not fetch SEC data here.
- Do not write directly to SQLite here.
- Do not calculate derived indicators such as growth, margins, ratios, total debt, or free cash flow here.

### `src/storage/`

SQLite persistence.

Current files:

- `database.py`: SQLite connection and schema initialization helpers.
- `facts_repository.py`: `RawFactRepository` for source-separated normalized
  raw XBRL observations, compact occurrence/conflict evidence, and raw-identity
  migration.
- `industry_labels_repository.py`: `CompanyIndustryLabelRepository` for persisted company hard-industry labels and evidence.
- `concept_mappings_repository.py`: `ConceptMappingRepository` for scoped approved learned raw-concept mappings used by hard mapping.
- `company_repository.py`: `CompanyRepository` and `CompanyRecord` for company identity and refresh state.
- `filings_repository.py`: `FilingRepository` and `FilingRecord` for ingested filing metadata and active-window state.
- `metrics_repository.py`: `FinancialMetricRepository` and `FinancialMetric` for mapped base financial metrics.
- `indicators_repository.py`: `FinancialIndicatorRepository` for persisted derived indicator rows.
- `retrieval_repository.py`: `RetrievalRepository`, `FilingChunk`, and `RetrievalIndexState` for canonical filing chunks and atomic current-generation state.
- `__init__.py`: Public exports for storage APIs.

Key responsibilities:

- Own local SQLite schema helpers.
- Persist Company Facts and Arelle observations as separate raw rows for the same accession and semantic fact identity.
- Persist reusable company industry labels and governed learned mapping decisions.
- Upsert facts using semantic identity plus accession and source; keep fiscal
  labels, form, and SEC frame as provenance rather than identity.
- Collapse equivalent same-accession occurrences with compact references, and
  quarantine conflicting values with retained conflict evidence.
- Retrieve stored facts by CIK and optional concept filters.
- Delete company-scoped raw facts, filing metadata, base metrics, derived indicators, retrieval chunks/state, and registry rows when reset orchestration requests it.
- Persist company registry records.
- Persist ingested filing metadata.
- Persist business-friendly base financial metrics mapped from raw XBRL facts.
- Persist derived financial indicators with formula versions, skipped reasons, source metric IDs, raw fact IDs, accession numbers, and active-window state.
- Persist active-window filing chunks with source hashes, resolved source paths, canonical sections, stable chunk IDs, and parser/splitter versions.
- Switch the current retrieval generation only after complete vector and BM25 artifacts exist.
- Track latest ingested filing dates and next-check dates for 10-K and 10-Q updates.
- Mark filings, base metrics, and derived indicators as active or inactive for the default inspection scope.
- Keep `raw_xbrl_facts` as the source-of-truth archive while active-window filters constrain normal metric retrieval.

Boundary rule:

- Storage should not fetch SEC data, normalize XBRL payloads, calculate indicators, run analytics, retrieve filing text, or call LLMs.

### `src/indicators/`

Derived financial indicator layer.

Current files:

- `__init__.py`: Public exports for the indicator engine.
- `engine.py`: Calculates the requested deterministic indicator catalog from base metrics and returns calculated or skipped indicator results. With `active_only=True`, it emits only active-window periods but may use stored out-of-window metrics as prior-period formula context.
- `formulas.py`: Formula registry with indicator names, formula text, formula version, required metrics, period type, and output unit.
- `models.py`: Indicator dataclasses and calculation status constants.

Current status:

- Indicator formula registry and deterministic engine are implemented.
- The engine calculates from `financial_metrics` inputs only and does not read or write SQLite.
- Results are persisted through `src/storage/indicators_repository.py`.

Responsibilities:

- Calculate the current requested indicator catalog, including growth, margin, return, cash generation, liquidity, leverage, operating-efficiency, and shareholder-impact indicators.
- Keep active-window indicator output separate from broader stored metric context needed for prior-period formulas.
- Treat `free_cash_flow` as a derived indicator from operating cash flow and capital expenditure, not as a raw fact or base metric.
- Preserve formula definitions, formula versions, source metric IDs, source raw fact IDs, and source accession numbers.
- Return skipped indicator rows with explicit reasons when inputs are missing, denominators are zero, units mismatch, prior comparable periods are missing, EBITDA is non-positive, or debt mapping is unsupported.

### `src/retrieval/`

Semantic filing retrieval layer.

Current files:

- `errors.py`: Named retrieval configuration, corpus, query, mismatch, and corruption errors.
- `models.py`: Parsed-section, index-sync, filing-summary, and retrieved-evidence dataclasses.
- `parser.py`: Visible Inline XBRL cleanup and form-aware 10-K/10-Q item extraction.
- `service.py`: Active-window synchronization, stable chunking, local index generation, integrity validation, hybrid retrieval, and artifact cleanup.
- `__init__.py`: Public retrieval exports.

Current status and responsibilities:

- Loads active-window 10-K and 10-Q HTML from stored filing records.
- Removes non-visible Inline XBRL content and extracts form-aware SEC sections.
- Uses LlamaIndex `SentenceSplitter`, local MiniLM embeddings, and a persisted BM25 index.
- Stores canonical chunks and lineage in SQLite while treating retrieval indexes as rebuildable generation artifacts.
- Reuses unchanged generations and preserves the last complete generation when a rebuild fails.
- Returns ranked evidence with component scores, fused rank, and complete filing lineage without calling Gemini.

### `src/analyze/`

LLM/RAG reasoning layer.

Current files:

- `industry_classification.py`: Gemini-backed hard-industry classifier for 10-K Item 1 Business, with strict label validation, high-confidence label keeping, and low-confidence label ignoring.
- `xbrl_formula_proposals.py`: Provider orchestration for report-only missing-target formula proposals through the ordered OpenAI `gpt-5-mini`, Gemini `gemini-3.1-flash-lite`, and Gemini `gemini-2.5-flash` panel; it supports single-target calls and statement-scoped batch calls, and provider failures are reported rather than persisted.
- `prompts.py`: Prompt templates, including the hard-industry classification prompt and statement-first single-target and statement-scoped batch XBRL formula proposal prompts.
- `__init__.py`: Package marker.

Current status:

- Gemini hard-industry classification is implemented for ingestion label assignment.
- Report-only XBRL formula proposal calls are implemented for the MS2.5 report.
  Formula proposal prompts use
  representative target-unit-compatible period contexts, statement-first
  component selection, optional evidence-backed zero-target decisions, and
  exact context cache reuse for successful structured decisions. Batch prompts
  may ask for multiple missing targets together only when they share the same
  target statement group and compatible raw-concept context.
- Gemini/RAG answer synthesis is not implemented yet.

Planned responsibilities:

- Keep all prompt templates in `prompts.py`.
- Use `gemini-2.5-flash` for reasoning and answer generation.
- Keep Gemini classification separate from deterministic XBRL concept mapping; classification assigns company labels only.
- Combine reported facts, derived indicators, analytics results, and retrieval evidence into grounded explanations.

## Planned But Not Currently Present

```text
src/analytics/
src/evaluation/
src/workflows/
```

`src/analytics/` is described in `proposal.md`, but it is not currently present
in the repository. When added, it should own deterministic financial analysis,
including trend, period comparison, outlier, volatility, and chart-ready outputs
without using the LLM.

`src/evaluation/` is described in `proposal.md`, but it is not currently
present in the repository. When added, it should own analysis-quality checks,
evidence-reference validation, and future manual evaluation of generated
analysis quality.

`src/workflows/` is described in `proposal.md`, but it is not currently present in the repository.

When added, it should own thin application workflow orchestration. For example, `src/workflows/company_ingestion.py` can call ingestion, processing, storage, retrieval, analytics, or analysis modules without duplicating their internal logic.

## Verification

The project uses focused pytest coverage alongside milestone experiments:

- Run the complete automated suite with `uv run python -m pytest -q`.
- The restored suite currently covers settings, SEC client behavior, ticker and
  submissions parsing, companyfacts normalization, XBRL periods and quality,
  hard industry labels and mapping targets, active-window base metric mapping,
  repositories, ingestion refresh paths, company deletion, indicator formulas
  and lineage, filing parsing, retrieval generation integrity and rollback,
  fused evidence lineage, API health, concise CLI reporting, and MS2/MS2.5
  experiment behavior.
- `tests/test_arelle_worker.py` uses the local `data/fixtures/arelle/` taxonomy
  to verify complete and failed result envelopes, JSON round trips, validation
  scoping, session closure, and child-process cleanup.
- `tests/test_arelle_inventory.py` copies that taxonomy into temporary storage
  and verifies sequential processing, exact warm-cache reuse with zero workers,
  visible failed-result reuse, acquisition and dependency hash checks, corrupt
  cache regeneration, internal and caller-declared external dependency repair,
  interrupted cache publication, and processing-contract invalidation.
- `tests/test_observation_reconciliation.py` uses typed source observations and
  Arelle result records to verify matches, numerical equivalence, conflicts,
  source-only supplements, ambiguity quarantine, blocked or unusable facts,
  metadata attribution, retained structural evidence, and accession scoping.
- `tests/test_accession_precedence.py` verifies latest-valid fact selection,
  invalid and omitted amendment handling, equivalent duplicate lineage,
  unresolved conflict quarantine, partial statement-network replacement,
  field-level concept metadata, and compatible mixed-accession components.
- Extend automated coverage when changing deterministic logic, repositories,
  public interfaces, regressions, or important failure paths.

- Use milestone experiment scripts under `experiments/MS*/` for human-readable
  workflow inspection.
- Inspect generated SQLite databases, filing downloads, CSV exports, and saved
  text or Markdown reports; terminal output should remain concise when the
  experiment defines a report artifact.
- Use `uv run python ...` for local scripts and experiment runs.

## Generated Or Local-Only Files

The following paths may exist locally but should not be treated as source architecture:

- `.venv/`
- `__pycache__/`
- `src/**/__pycache__/`
- `stock_data.db`
- downloaded files under `data_store/filings/`
- generated knowledge cache files under `data_store/knowledge/`, including formula proposal cache entries
- generated exports under `data/exports/`
- generated shared experiment storage under `experiments/storage/`, including `experiment.db` and `filings/`
- generated Milestone 2.5 report artifacts: `experiments/MS2_5/milestone25_mapping_report_*.md`
- generated Milestone 3 report artifacts: `experiments/MS3/milestone3_indicator_report_*.txt`
- generated Milestone 5 report artifacts: `experiments/MS5/experiment_report_*.txt`
- local task notes in `to_do.md`
- completed root `plan*.txt` milestone notes retained locally or in Git history

## Update Rule

When the repository structure changes:

1. Update this file first if the change affects folders, modules, file responsibilities, generated storage locations, or verification workflows.
2. Update `proposal.md` only if the change affects product scope, milestones, or architecture direction.
3. Keep completed root `plan*.txt` notes local-only; preserve durable current rules in the appropriate source-of-truth document.
4. Do not list cache files, virtual environments, or generated runtime data as architecture.
