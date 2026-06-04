# System Structure

## Role

This file is the current source of truth for the repository and module structure of the system.

Keep this file updated whenever:

- a top-level folder or important file is added, removed, or renamed
- a `src/` module responsibility changes
- a planned module becomes implemented
- generated storage locations change
- tests are added for a new system layer

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
  +-- src/ingestion/filings.py        -> download 10-K and 10-Q filing HTML
  +-- src/processing/xbrl_normalizer.py
  |     -> normalize companyfacts into NormalizedFact records
  +-- src/processing/active_window.py
  |     -> select latest 5 annual and latest 12 quarterly active periods
  +-- src/processing/base_metrics.py
  |     -> map clean raw facts into business-friendly base metrics
  |
  +-- src/storage/facts_repository.py
  |     -> persist normalized facts in SQLite
  +-- src/storage/company_repository.py
  |     -> persist company registry and refresh state
  +-- src/storage/filings_repository.py
  |     -> persist filing inventory and active-window state
  +-- src/storage/metrics_repository.py
        -> persist mapped base financial metrics

Generated local data:

data_store/filings/          downloaded SEC filing HTML
stock_data.db                SQLite database
  raw_xbrl_facts             normalized XBRL facts table
  companies                  local company registry
  filings                    ingested filing inventory
  financial_metrics          base metrics mapped from raw XBRL facts
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
  |                            companies, filings, and base metrics
  +-- src/indicators/         planned derived financial indicators
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
  tests/
  stock_data.db
```

## Top-Level Responsibilities

- `.gitignore`: Git ignore rules.
- `README.md`: Local setup, run, and test notes.
- `agents.md`: Project instructions for coding agents.
- `config.env`: Local configuration and secrets. Do not treat as public documentation.
- `discussion.txt`: Architecture discussion, follow-up questions, and decision notes.
- `experiments/`: Milestone experiment folders, local experiment proposals, and future runnable experiment scripts. Explicit milestone experiment designs live in each `experiments/MS*/experiment_proposal.md` file.
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

- `data/fixtures/`: Saved SEC API responses and sample data used by tests. Treat fixtures as immutable test inputs.
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
  MS1/
    experiment_proposal.md
  MS2/
    experiment_proposal.md
    milestone2_ingestion_showcase.py
  MS2_5/
    experiment_proposal.md
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
- `experiments/MS2_5/experiment_proposal.md`: Human-inspection proposal for the Milestone 2.5 company registry, update-check, active-window, and base-metric experiment. It defines existing-company, new-company, and repeated-run cases.
- `experiments/MS3/experiment_proposal.md`: Human-inspection proposal for the Milestone 3 indicator engine experiment. It defines formula, skipped-period, and source-metric traceability output.
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
- `filings.py`: Filing metadata selection and filing document download.
- `refresh_policy.py`: Next-check date heuristics for 10-K and 10-Q refresh checks.
- `company.py`: `ingest_company` orchestration and `CompanyIngestionResult`.
- `company.py`: also exposes `delete_ingested_company` for local company reset/delete orchestration.
- `errors.py`: SEC ingestion error types.
- `__init__.py`: Public exports for ingestion APIs.

Key responsibilities:

- Resolve ticker symbols to CIKs.
- Retrieve SEC submissions and companyfacts JSON.
- Select latest relevant 10-K and 10-Q filings.
- Download filing documents.
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
- Store the common supported `us-gaap` concept list for 10-K and 10-Q forms by default.
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
- `__init__.py`: Public exports for storage APIs.

Key responsibilities:

- Own local SQLite schema helpers.
- Persist normalized raw XBRL facts.
- Upsert facts using a stable uniqueness key.
- Retrieve stored facts by CIK and optional concept filters.
- Delete company-scoped raw facts, filing metadata, base metrics, and registry rows when reset orchestration requests it.
- Persist company registry records.
- Persist ingested filing metadata.
- Persist business-friendly base financial metrics mapped from raw XBRL facts.
- Track latest ingested filing dates and next-check dates for 10-K and 10-Q updates.
- Mark filings and base metrics as active or inactive for the default inspection scope.
- Keep `raw_xbrl_facts` as the source-of-truth archive while active-window filters constrain normal metric retrieval.

Boundary rule:

- Storage should not fetch SEC data, normalize XBRL payloads, calculate indicators, run analytics, retrieve filing text, or call LLMs.

### `src/indicators/`

Derived financial indicator layer.

Current files:

- `__init__.py`: Package marker.

Current status:

- Folder exists as a placeholder.
- Indicator formulas are not implemented yet.

Planned responsibilities:

- Calculate derived indicators such as revenue growth, margins, debt ratio, current ratio, free cash flow, and cash conversion.
- Preserve formula definitions and source fact references.

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
- Support future regression tests for generated analysis quality.

## Planned But Not Currently Present

```text
src/workflows/
```

`src/workflows/` is described in `proposal.md`, but it is not currently present in the repository.

When added, it should own thin application workflow orchestration. For example, `src/workflows/company_ingestion.py` can call ingestion, processing, storage, retrieval, analytics, or analysis modules without duplicating their internal logic.

## Tests

```text
tests/
  test_base_metrics.py
  test_company_deletion.py
  test_company_ingestion.py
  test_companyfacts.py
  test_facts_repository.py
  test_filings.py
  test_health.py
  test_main.py
  test_milestone2_experiment.py
  test_plan25_repositories.py
  test_sec_client.py
  test_settings.py
  test_submissions.py
  test_tickers.py
  test_xbrl_normalizer.py
  test_xbrl_periods.py
  test_xbrl_quality.py
```

Current coverage areas:

- Settings loading and model configuration.
- FastAPI health route.
- SEC client behavior.
- Ticker mapping and ticker-to-CIK resolution.
- Submissions and companyfacts retrieval helpers.
- Filing metadata selection and filing download helpers.
- XBRL normalization, periods, and quality flags.
- Active analysis window selection and base metric mapping.
- SQLite raw fact repository.
- SQLite company, filing, and financial metric repositories.
- Company-level ingestion orchestration.
- Company-level reset/delete orchestration.
- Root `main.py` report formatting.
- Milestone 2 experiment CLI behavior for fixture mode, unsupported fixture tickers, and missing live SEC configuration.

## Generated Or Local-Only Files

The following paths may exist locally but should not be treated as source architecture:

- `.venv/`
- `.pytest_cache/`
- `__pycache__/`
- `src/**/__pycache__/`
- `tests/__pycache__/`
- `stock_data.db`
- downloaded files under `data_store/filings/`
- generated exports under `data/exports/`

## Update Rule

When the repository structure changes:

1. Update this file first if the change affects folders, modules, file responsibilities, generated storage locations, or tests.
2. Update `proposal.md` only if the change affects product scope, milestones, or architecture direction.
3. Keep `plan1.txt` and `plan2.txt` historical unless correcting those specific milestone notes.
4. Do not list cache files, virtual environments, or generated runtime data as architecture.
