# System Structure

## Role

This file is the source of truth for the repository's currently implemented
modules, runtime flows, storage locations, generated artifacts, and verification
commands.

It does not define future architecture. Use `proposal.md` for overall direction,
`docs/milestones/` for high-fidelity milestone designs, and `docs/policies/` for
durable mechanisms. An `approved` or `active` milestone may describe behavior
that is not yet wired into the runtime.

## Current Runtime Overview

### Public company-ingestion flow

```text
ticker
  -> ticker/CIK and SEC submissions lookup
  -> current company registry and refresh decision
  -> Company Facts normalization
  -> active 10-K/10-Q filing inventory and optional Inline XBRL enrichment
  -> current hard-label and approved mapping workflow
  -> financial_metrics
  -> deterministic financial_indicators
  -> SQLite
```

The public entry point remains `src.ingestion.company.ingest_company()`. This
legacy runtime still uses active annual/quarterly windows and is not yet replaced
by the approved annual-only MS2/MS3 workflow.

### Implemented MS2/MS3 seams

```text
complete annual submissions discovery
  -> sequential one-accession Arelle workers
  -> exact per-accession result cache
  -> typed source observations
  -> Arelle/Company Facts reconciliation
  -> latest-valid accession/network/metadata precedence
  -> immutable fiscal-period industry-label snapshots
  -> approved direct mapping and exact missing targets
  -> shadow mapping candidates
  -> nonnumeric semantic evidence groups
  -> three blind judge calls and immutable recommendation history
  -> period-specific formula/zero application
  -> immutable recovery applications and recovered financial metrics
```

These seams are additive and tested, but the complete annual workflow is not yet
wired into `ingest_company()`. Atomic annual publication and the combined
real-company acceptance proof are not implemented.

### Retrieval flow

```text
active local filing HTML
  -> visible filing-text cleanup and SEC section parsing
  -> stable chunks in SQLite
  -> local vector and BM25 index generations
  -> fused ranked RetrievedEvidence with filing lineage
```

Retrieval does not generate answers. General RAG synthesis and deterministic
financial analysis are not implemented.

## Top-Level Layout

```text
src/                    application source
tests/                  automated tests
data/fixtures/          immutable local test inputs
data/exports/           generated CSV exports
data_store/             generated filings and knowledge artifacts
experiments/            human-inspection scripts and generated state
docs/                   structure, policies, milestones, and runbook
proposal.md             project direction and roadmap
CONTEXT.md              canonical domain glossary
agents.md               coding-agent contract
```

## Documentation

```text
docs/
  structure.md
  experiments.md
  milestones/
    README.md
    MS1-foundation.md
    MS2-annual-xbrl-ingestion.md
    MS3-base-metric-mapping.md
    MS4-indicators.md
    MS6-filing-retrieval.md
  policies/
    mapping.md
  diagrams/
    MS2-ingestion.*
    MS3-mapping.*
```

- `docs/milestones/README.md` owns milestone navigation and status.
- A milestone file owns one subproject's approved high-fidelity design.
- `docs/policies/mapping.md` owns durable mapping governance.
- `docs/experiments.md` owns shared experiment conventions, not milestone
  designs.
- `CONTEXT.md` contains domain language only.

## Source Layers

### Configuration and API

- `src/config/settings.py`: environment-backed settings, paths, model choices,
  SEC identity, and feature configuration.
- `src/api/main.py`: FastAPI application, health route, and thin API boundary.
- `src/model_defaults.py`: shared model defaults for classifier, legacy
  report-only proposals, and production judges.

The API does not yet expose the complete planned ingestion, metric, retrieval,
analysis, and Q&A surface.

### SEC and filing ingestion

`src/ingestion/` owns external acquisition and company-level coordination:

- `sec_client.py`, `tickers.py`, `submissions.py`, `companyfacts.py`, and
  `filings.py` implement SEC-facing behavior.
- `company.py` owns the current public company-ingestion orchestration.
- `inline_xbrl.py` loads current Inline XBRL evidence.
- `refresh_policy.py` owns current refresh-date calculations.
- `arelle_worker.py` is the isolated one-accession Arelle process boundary.
- `arelle_inventory.py` processes the selected annual inventory sequentially
  with exact cache validation.
- `industry_labels.py` coordinates immutable fiscal-period label snapshots for
  the MS2 seam.

SEC request logic remains separate from database repositories.

### XBRL processing and metric mapping

`src/processing/` owns deterministic normalization and evidence transformation:

- Company Facts/Inline normalization, period handling, and quality flags
- typed Arelle extraction records and serializable evidence
- observation reconciliation and accession/network/metadata precedence
- shared SEC CIK identity comparison
- target catalogs, approved direct mapping, and exact missing targets
- inspectable shadow candidates
- legacy report-only formula/metric-coverage diagnostics
- MS3 semantic packets, grouping, response schemas, and canonical comparison
- period-specific formula/zero validation and component lineage

`direct_metric_mapping.py` can create only approved direct metric observations.
`semantic_recommendations.py` compares structured judge decisions.
`recovery_applications.py` independently resolves and validates each period,
calculates only unanimous addition/subtraction formulas or affirmative zeros,
and creates no metric directly. Formula components must match the requested
actual period and retain blocking Arelle diagnostics when rejected. Zero
requires a cited semantic concept backed by an actual precedence-selected
Arelle fact whose value is zero for the same company and accounting context.

### Model-facing analysis

`src/analyze/` currently contains:

- industry classification
- centralized prompt templates
- structured provider transport
- legacy report-only formula proposal adapters
- production semantic judge adapters

The three production judges receive identical nonnumeric packets through the
thin semantic-recommendation workflow. General filing Q&A, thesis synthesis, and
risk interpretation are not implemented.

### Indicators

`src/indicators/` contains the 28-definition deterministic formula registry,
models, and engine. The engine:

- reads `financial_metrics` inputs
- keeps annual/quarterly period types separate
- preserves source metric/raw-fact/accession lineage
- emits explicit skipped results
- does not read or write SQLite directly

`src/storage/indicators_repository.py` persists results. The current local
evidence has complete annual rows for several companies but no validated
quarterly indicator data, so the indicator milestone remains active.

### Filing retrieval

`src/retrieval/` owns visible filing parsing, section-aware chunking, generation
integrity, local vector/BM25 indexes, fused ranking, and retrieved-evidence
lineage. SQLite owns canonical chunks and generation state; index files remain
rebuildable artifacts.

### Storage

`src/storage/database.py` initializes SQLite. Focused repositories own:

- companies and filing inventory
- raw XBRL facts
- financial metrics and indicators
- fiscal-period industry labels
- approved learned mappings
- shadow mapping candidates
- semantic recommendation history
- period-specific recovery application history
- filing chunks and retrieval generation state

Important tables include:

```text
companies
filings
raw_xbrl_facts
company_industry_labels
xbrl_concept_mappings
mapping_shadow_candidates
semantic_recommendation_records
recovery_application_records
financial_metrics
financial_indicators
filing_chunks
retrieval_index_state
```

Current raw-fact identity and company refresh fields still follow the legacy
schema. The approved MS2/MS3 migration has not been published.

### Workflows

`src/workflows/semantic_recommendations.py` reuses an exact stored semantic
group or calls the three configured judges concurrently, compares their
responses, and persists immutable attempt history.

`src/workflows/recovery_applications.py` persists period applications and
creates `financial_metrics` only for successful formula/zero applications.
Persistence rechecks the canonical expression, calculated value, target unit
family, and stored raw-fact lineage before publishing a recovered metric.
Recovered metrics carry an explicit origin and point to their application;
direct metrics must retain raw-observation lineage. The workflow verifies the
storage company against the recovery application's CIK and assigns recovered
accession lineage from the source with the latest filing date. Company-wide
atomic publication remains a later MS3 seam.

Keep future workflow modules thin.

## Experiments

```text
experiments/
  storage/                 generated shared database and filings
  MS2/ingestion_showcase.py
  MS3/mapping_inspection.py
  MS4/indicator_engine.py
  MS6/retrieval_pipeline.py
```

Milestone acceptance requirements live in the corresponding plan. Shared
execution and report conventions live in `docs/experiments.md`.

## Data and Generated Storage

- `data/fixtures/`: immutable SEC and Arelle fixtures.
- `data/exports/`: generated CSV output.
- `data_store/filings/`: downloaded source filings.
- `data_store/knowledge/`: generated Arelle, proposal, vector, and keyword
  cache/index artifacts.
- `experiments/storage/`: generated shared experiment database and filings.

Local/generated files are not source architecture:

- `.venv/`, `__pycache__/`, and `*.pyc`
- `config.env` and provider credentials
- `stock_data.db` and experiment databases
- downloaded filings and knowledge caches
- generated CSVs
- MS3 mapping reports
- MS4 indicator reports
- MS6 retrieval reports
- local task notes

Do not modify raw fixtures or downloaded source filings unless the task
explicitly requires it.

## Verification

Complete automated suite:

```powershell
uv run python -m pytest -q
```

Important focused surfaces:

```powershell
uv run python -m pytest -q tests/test_arelle_worker.py tests/test_arelle_inventory.py
uv run python -m pytest -q tests/test_observation_reconciliation.py tests/test_accession_precedence.py
uv run python -m pytest -q tests/test_direct_metric_mapping.py tests/test_semantic_evidence.py
uv run python -m pytest -q tests/test_semantic_recommendation_workflow.py
uv run python -m pytest -q tests/test_recovery_applications.py tests/test_recovery_application_persistence.py
uv run python -m pytest -q tests/test_indicators.py tests/test_retrieval.py
```

Use the experiment commands in `docs/experiments.md` for human-readable
evidence. A milestone is not completed from green unit tests alone when its plan
requires real filing/report inspection.

## Update Rules

1. Update this file when implemented modules, responsibilities, storage,
   generated artifacts, or verification workflows change.
2. Update `proposal.md` only for project direction, roadmap, or scope changes.
3. Update the owning milestone plan when its accepted contract, status, or
   completion evidence changes.
4. Update a policy only when the durable mechanism changes.
5. Preserve obsolete drafts in Git history rather than an active archive.
6. Never describe an approved future design here as already implemented.
