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

Use `plan1.txt`, `plan2.txt`, `plan2.5.txt`, and `plan3.txt` as milestone notes. Do not treat old plan files as the current structure source of truth.

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
  +-- src/processing/xbrl_normalizer.py
  |     -> normalize companyfacts into NormalizedFact records
  +-- src/processing/active_window.py
  |     -> select latest 5 annual and latest 12 quarterly active periods
  +-- src/processing/base_metrics.py
  |     -> map clean raw facts into business-friendly base metrics
  +-- src/indicators/engine.py
  |     -> calculate deterministic derived indicators from active base metrics
  |
  +-- src/storage/facts_repository.py
  |     -> persist normalized facts in SQLite
  +-- src/storage/company_repository.py
  |     -> persist company registry and refresh state
  +-- src/storage/filings_repository.py
  |     -> persist filing inventory and active-window state
  +-- src/storage/metrics_repository.py
  |     -> persist mapped base financial metrics
  +-- src/storage/indicators_repository.py
        -> persist derived financial indicators and skipped calculations

Generated local data:

data_store/filings/          downloaded SEC filing HTML
stock_data.db                SQLite database
  raw_xbrl_facts             normalized XBRL facts table
  companies                  local company registry
  filings                    ingested filing inventory
  financial_metrics          base metrics mapped from raw XBRL facts
  financial_indicators       derived indicators with formulas and traceability
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
  |                            companies, filings, base metrics, and indicators
  +-- src/indicators/         deterministic derived financial indicators
  +-- src/analytics/          planned deterministic financial analysis
  +-- src/retrieval/          planned filing chunking and evidence retrieval
  +-- src/analyze/            planned Gemini/RAG answer synthesis
  +-- src/evaluation/         planned analysis-quality checks
```

### Evidence Flow Goal

```text
SEC filings and companyfacts
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
Deterministic financial analysis
  |
  +------------------------------+
  |                              v
  |                      Semantic filing evidence
  |                              |
  +--------------+---------------+
                 v
        Grounded LLM explanation
```

The important rule is that each box should remain traceable. Reported facts, calculated indicators, deterministic analysis, filing evidence, and LLM interpretations should not be blended together without labels.

## Current Top-Level Structure

```text
.
  .gitignore
  README.md
  agents.md
  config.env
  discussion.txt
  main.py
  plan1.txt
  plan2.txt
  plan2.5.txt
  plan3.txt
  proposal.md
  pyproject.toml
  to_do.txt
  uv.lock
  data/
  data_store/
  docs/
  experiments/
  src/
  stock_data.db
```

## Top-Level Responsibilities

- `.gitignore`: Git ignore rules.
- `README.md`: Local setup and run notes.
- `agents.md`: Project instructions for coding agents.
- `config.env`: Local configuration and secrets. Do not treat as public documentation.
- `discussion.txt`: Architecture discussion, follow-up questions, and decision notes.
- `experiments/`: Milestone experiment folders, local experiment proposals, runnable experiment scripts, and shared generated experiment storage. Explicit milestone experiment designs live in each `experiments/MS*/experiment_proposal.md` file.
- `main.py`: Local CLI-style script that runs company ingestion and prints a SEC/XBRL ingestion report.
- `plan1.txt`: Historical Milestone 1 scaffold plan.
- `plan2.txt`: Historical SEC/XBRL ingestion and normalization milestone plan.
- `plan2.5.txt`: Company registry, filing inventory, update state, active-window policy, and base metric mapping milestone.
- `plan3.txt`: Planned indicator engine milestone for deterministic derived indicators, formula traceability, and indicator storage.
- `proposal.md`: Current product scope, architecture direction, and MVP roadmap.
- `pyproject.toml`: Python project metadata and dependencies.
- `to_do.txt`: Local task notes.
- `uv.lock`: Locked dependency versions for `uv`.
- `stock_data.db`: Local generated SQLite database. This is runtime data, not source architecture.

## Data And Storage

```text
data/
  exports/
  fixtures/

data_store/
  filings/
```

- `data/fixtures/`: Saved SEC API responses and sample data. Treat fixtures as immutable inputs.
- `data/exports/`: Generated CSV export location.
- `data_store/filings/`: Downloaded SEC filing documents.

## Documentation

```text
docs/
  experiments.md
  structure.md
```

- `docs/experiments.md`: Central experiment runbook and index. It defines shared experiment rules, data modes, folder naming, and links to per-milestone proposal files.
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
  MS4/
    experiment_proposal.md
  MS5/
    experiment_proposal.md
  MS6/
    experiment_proposal.md
  MS7/
    experiment_proposal.md
```

- `experiments/MS1/experiment_proposal.md`: Human-inspection proposal for the Milestone 1 scaffold experiment. It defines the local project structure, settings, and API health output to inspect.
- `experiments/MS2/experiment_proposal.md`: Human-inspection proposal for the Milestone 2 SEC/XBRL ingestion and normalization experiment. It defines input cases, intended terminal output, artifacts to inspect, edge cases, and expected outcomes.
- `experiments/MS2/milestone2_ingestion_showcase.py`: Runnable Milestone 2 experiment script that prints the SEC/XBRL ingestion and normalization showcase described by the Milestone 2 proposal.
- `experiments/storage/`: Generated shared experiment storage. Current MS2.5 live runs use `experiments/storage/experiment.db` and `experiments/storage/filings/` so later milestone experiments can inspect the same isolated state without touching `stock_data.db`.
- `experiments/MS2_5/experiment_proposal.md`: Human-inspection proposal for the Milestone 2.5 Plan 2.5 ingestion manual examination harness. It defines one user-chosen ticker per run, persistent shared isolated experiment storage, setup ingestion, already-ingested session inspection, 10-K and 10-Q update-check evidence, active-window evidence, raw fact mapping coverage, unknown and alternate SEC/XBRL tag evidence, financial metric data lineage output appended to the saved report, saved compact report output, optional detailed Markdown sections in the saved report, and full SQLite/CSV evidence artifacts.
- `experiments/MS2_5/milestone25_live_sec_inspection.py`: Runnable Milestone 2.5 experiment script that saves `experiments/MS2_5/experiment_report.md` by default without printing the report body to the terminal, separates setup ingestion from the already-ingested session check, reports company-local existence, refresh due status, SEC check behavior, newly ingested filings, and next check dates, appends raw fact mapping coverage, unmapped/alternate SEC/XBRL tag evidence, and annual/quarterly pivoted XBRL metric tables with padded columns and presentation-only per-period `k`/`m` suffixes to the saved report, includes detailed Markdown sections in the saved report with `--full-report`, accepts `--write-report` as a compatibility flag, preserves `experiments/storage/experiment.db` across runs, writes isolated filing downloads under `experiments/storage/filings/`, and exports supporting CSVs under `data/exports/ms2_5/`.
- `experiments/MS3/experiment_proposal.md`: Human-inspection proposal for the Milestone 3 indicator engine experiment. It defines active accession-window scope, yearly and quarterly indicator tables for the requested catalog, skipped-period reasons, formulas, and source-metric traceability output.
- `experiments/MS3/milestone3_indicator_engine.py`: Runnable Milestone 3 experiment script that reads stored `financial_indicators` and writes a `.txt` report under `experiments/MS3` with active accession-window scope, yearly and quarterly indicator tables for the requested ticker or tickers, skipped reasons, formulas, and source traceability.
- `experiments/MS4/experiment_proposal.md`: Human-inspection proposal for the Milestone 4 deterministic financial analytics experiment. It defines trend, comparison, gap, outlier, and chart-ready output.
- `experiments/MS5/experiment_proposal.md`: Human-inspection proposal for the Milestone 5 retrieval pipeline experiment. It defines chunking, retrieval metadata, score, source-path, and preview output.
- `experiments/MS6/experiment_proposal.md`: Human-inspection proposal for the Milestone 6 Gemini integration experiment. It defines model, prompt-source, prompt-preview, and call-metadata output.
- `experiments/MS7/experiment_proposal.md`: Human-inspection proposal for the Milestone 7 RAG analysis experiment. It defines evidence inventory, answer section separation, references, and unsupported-claim checks.

Runnable experiment scripts should live inside the same milestone folder as
their proposal when implemented.

## Source Modules

```text
src/
  __init__.py
  analytics/
  analyze/
  api/
  config/
  evaluation/
  indicators/
  ingestion/
  processing/
  retrieval/
  storage/
```

### `src/config/`

Runtime configuration loading.

Current files:

- `settings.py`: Defines `Settings`, model configuration validation, and `load_settings`.
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
- `submissions.py`: SEC submissions URL building and retrieval.
- `companyfacts.py`: SEC companyfacts URL building and retrieval.
- `filings.py`: Filing metadata listing, latest-form selection helpers, and filing document download.
- `refresh_policy.py`: Next-check date heuristics for 10-K and 10-Q refresh checks, plus business-day helpers.
- `company.py`: Refresh-aware `ingest_company` orchestration and `CompanyIngestionResult`.
- `company.py`: also exposes `delete_ingested_company` for local company reset/delete orchestration.
- `errors.py`: SEC ingestion error types.
- `__init__.py`: Public exports for ingestion APIs.

Key responsibilities:

- Resolve ticker symbols to CIKs.
- Retrieve SEC submissions and companyfacts JSON.
- Check local company registry state before live SEC ingestion.
- Reuse local company data when refresh is not due.
- Check SEC submissions when refresh is due and preserve local data if the refresh fails.
- Select active-window 10-K and 10-Q filings from the latest 5 annual and latest 12 quarterly fact periods.
- Download missing active-window filing documents and reuse already downloaded filing documents.
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

XBRL/companyfacts normalization, active-window selection, and deterministic base metric mapping.

Current files:

- `xbrl_normalizer.py`: Defines `NormalizedFact`, `normalize_companyfacts`, `normalize_fact_entry`, and duplicate fact marking.
- `active_window.py`: Selects the active analysis window: latest 5 fiscal years of 10-K data and latest 12 quarters of 10-Q data.
- `base_metrics.py`: Maps clean supported raw XBRL facts into business-friendly base metric records.
- `concepts.py`: Supported concepts, taxonomies, and forms.
- `periods.py`: SEC date parsing and period classification helpers.
- `quality.py`: Quality flag constants and helpers.
- `errors.py`: XBRL processing error types.
- `__init__.py`: Public exports for processing APIs.

Key responsibilities:

- Normalize SEC companyfacts into auditable fact records.
- Support broad raw-archive normalization across all requested forms, taxonomies, and concepts.
- Keep the common supported `us-gaap` concept list for selective metric mapping and reporting, not as the raw archive limit.
- Preserve raw values separately from parsed numeric values.
- Normalize CIK, taxonomy, concept, unit, periods, fiscal year/period, form, filing date, accession number, frame, and source metadata.
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
- `facts_repository.py`: `RawFactRepository` for normalized raw XBRL facts.
- `company_repository.py`: `CompanyRepository` and `CompanyRecord` for company identity and refresh state.
- `filings_repository.py`: `FilingRepository` and `FilingRecord` for ingested filing metadata and active-window state.
- `metrics_repository.py`: `FinancialMetricRepository` and `FinancialMetric` for mapped base financial metrics.
- `indicators_repository.py`: `FinancialIndicatorRepository` for persisted derived indicator rows.
- `__init__.py`: Public exports for storage APIs.

Key responsibilities:

- Own local SQLite schema helpers.
- Persist normalized raw XBRL facts.
- Upsert facts using a stable uniqueness key.
- Retrieve stored facts by CIK and optional concept filters.
- Delete company-scoped raw facts, filing metadata, base metrics, derived indicators, and registry rows when reset orchestration requests it.
- Persist company registry records.
- Persist ingested filing metadata.
- Persist business-friendly base financial metrics mapped from raw XBRL facts.
- Persist derived financial indicators with formula versions, skipped reasons, source metric IDs, raw fact IDs, accession numbers, and active-window state.
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

### `src/analytics/`

Deterministic financial analysis layer.

Current files:

- `__init__.py`: Package marker.

Current status:

- Folder exists as a placeholder.
- Financial analytics are not implemented yet.

Planned responsibilities:

- Analyze raw facts and derived indicators without using the LLM.
- Produce trend, period comparison, outlier, volatility, and chart-ready outputs.

### `src/retrieval/`

Semantic filing retrieval layer.

Current files:

- `__init__.py`: Package marker.

Current status:

- Folder exists as a placeholder.
- Filing chunking, indexing, and retrieval are not implemented yet.

Planned responsibilities:

- Load and chunk SEC filing text.
- Store filing chunk metadata.
- Build retrieval indexes using LlamaIndex tools where suitable.
- Retrieve relevant filing evidence for analysis and Q&A.

### `src/analyze/`

LLM/RAG reasoning layer.

Current files:

- `prompts.py`: Placeholder for prompt templates.
- `__init__.py`: Package marker.

Current status:

- Prompt location exists.
- Gemini/RAG orchestration is not implemented yet.

Planned responsibilities:

- Keep all prompt templates in `prompts.py`.
- Use `gemini-2.5-flash` for reasoning and answer generation.
- Combine reported facts, derived indicators, analytics results, and retrieval evidence into grounded explanations.

### `src/evaluation/`

Evaluation and quality checks.

Current files:

- `__init__.py`: Package marker.

Current status:

- Folder exists as a placeholder.
- Evaluation scripts are not implemented yet.

Planned responsibilities:

- Check analysis quality.
- Validate evidence references.
- Support future manual evaluation of generated analysis quality.

## Planned But Not Currently Present

```text
src/workflows/
```

`src/workflows/` is described in `proposal.md`, but it is not currently present in the repository.

When added, it should own thin application workflow orchestration. For example, `src/workflows/company_ingestion.py` can call ingestion, processing, storage, retrieval, analytics, or analysis modules without duplicating their internal logic.

## Verification

This project does not maintain an automated `tests/` suite. Verification is
manual and experiment-driven:

- Use milestone experiment scripts under `experiments/MS*/` for human-readable
  workflow inspection.
- Inspect generated SQLite databases, filing downloads, CSV exports, terminal
  reports, and optional Markdown reports.
- Use `uv run python ...` for local scripts and experiment runs.
- Do not add pytest files unless the project testing policy changes again.

## Generated Or Local-Only Files

The following paths may exist locally but should not be treated as source architecture:

- `.venv/`
- `__pycache__/`
- `src/**/__pycache__/`
- `stock_data.db`
- downloaded files under `data_store/filings/`
- generated exports under `data/exports/`
- generated shared experiment storage under `experiments/storage/`, including `experiment.db` and `filings/`
- generated Milestone 2.5 report artifact: `experiments/MS2_5/experiment_report.md`
- generated Milestone 3 report artifacts: `experiments/MS3/milestone3_indicator_report_*.txt`

## Update Rule

When the repository structure changes:

1. Update this file first if the change affects folders, modules, file responsibilities, generated storage locations, or verification workflows.
2. Update `proposal.md` only if the change affects product scope, milestones, or architecture direction.
3. Keep `plan1.txt` and `plan2.txt` historical unless correcting those specific milestone notes.
4. Do not list cache files, virtual environments, or generated runtime data as architecture.
