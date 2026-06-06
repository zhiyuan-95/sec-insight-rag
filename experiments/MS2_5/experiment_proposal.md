# Milestone 2.5 Experiment Proposal: Plan 2.5 Ingestion Manual Examination

## Purpose

This experiment is the official manual examination harness for the new Plan 2.5
company ingestion workflow. It lets a human inspect what the actual
`ingest_company()` workflow creates, reuses, refreshes, and preserves for one
manually chosen company.

The experiment uses live SEC behavior and isolated local storage. It should not
mutate the real project database.

The experiment presents evidence. It does not decide success, failure, or
partial success. The project owner reviews the generated report, SQLite
database, and CSV exports, then judges whether the behavior looks correct.

Plan 2.5 ingestion owns the company-level workflow between raw SEC/XBRL facts
and future derived indicators:

```text
company request
  -> local company registry and refresh-state check
    -> live SEC initialization or refresh when needed
      -> full raw_xbrl_facts archive
        -> active 10-K/10-Q filing evidence
          -> active-window financial_metrics
```

The experiment should show whether a chosen ticker can be initialized through
the real ingestion workflow, then inspected as an already-ingested company so
the local refresh decision, SEC check behavior, newly ingested filings, and next
check dates are visible.

## Human Question

For a company I choose, what does Plan 2.5 ingestion do during setup and during
the next already-ingested session: local existence, refresh due status, SEC
update check, newly ingested filings, next check dates, and stored evidence?

## Milestone Scope

This experiment covers:

- one manually chosen ticker per run
- the actual `src.ingestion.ingest_company()` workflow
- live SEC company initialization through Plan 2.5 ingestion
- isolated experiment storage
- first-time setup ingestion
- already-ingested session inspection after setup
- company registry state
- filing inventory state
- full normalized SEC companyfacts archive in `raw_xbrl_facts`
- latest ingested 10-K and 10-Q filing dates
- next-check dates for 10-K and 10-Q refresh checks
- active analysis window state
- active filing evidence for the latest 5 fiscal years of 10-K data and latest
  12 quarters of 10-Q data
- base financial metric mapping
- traceability from `financial_metrics` to `raw_xbrl_facts` and filings
- compact terminal summary with full rows available in SQLite and CSV exports

This experiment does not cover derived indicators, deterministic analytics,
retrieval indexes, Gemini calls, RAG answers, frontend behavior, or pass/fail
grading.

## Recommended Location

```text
experiments/MS2_5/
  experiment_proposal.md
  milestone25_live_sec_inspection.py
  experiment.db
  filings/

data/exports/ms2_5/
  companies.csv
  filings.csv
  raw_xbrl_facts.csv
  financial_metrics.csv
  metric_traceability_sample.csv
```

The experiment should print a compact terminal summary by default.
`experiment.db` and the CSV exports should overwrite stable paths on each run.
The detailed Markdown report should be printed only when the user asks for it
with `--full-report`. `experiment_report.md` should be written only when the
user asks for the saved Markdown artifact with `--write-report`.

## Data Mode

This experiment uses live SEC behavior and isolated local storage.

```text
live
  Contacts SEC for the chosen ticker.
  Requires SEC_USER_AGENT.
  May observe different SEC data depending on the run date.

isolated local storage
  Writes to experiments/MS2_5/experiment.db.
  Writes filing downloads to experiments/MS2_5/filings/.
  Does not write to the real stock_data.db.
  Does not write filing downloads to the real data_store/filings/ path.
  Keeps the experiment database after the run for manual SQLite inspection.
```

The experiment should not use the real project database as its write target.
That keeps first-time ingestion, refresh-date generation, active-window
selection, and filing evidence storage inspectable without changing real local
company state.

## Command

Default run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER
```

Saved Markdown report run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER --write-report
```

Detailed Markdown terminal report run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER --full-report
```

Rules:

- exactly one ticker is accepted per run
- the compact summary is printed to the terminal by default
- `--full-report` prints the detailed Markdown report to the terminal
- `--write-report` writes the detailed Markdown report to `experiment_report.md`
- both 10-K and 10-Q behavior are presented for that ticker
- hidden test/support options may override the database, report, filings, and
  export paths, but normal use should rely on the stable paths above

## Report And Evidence Artifacts

Main report output:

```text
compact terminal stdout
```

Kept SQLite artifact:

```text
experiments/MS2_5/experiment.db
```

Supporting CSV artifacts:

```text
data/exports/ms2_5/
```

The compact terminal report should show the operational decision path first:
whether the company is local, whether an update check is due this session,
whether SEC was checked, whether new filing data was ingested, and the next
10-K/10-Q check dates after the session. Full rows should remain available in
`experiment.db` and CSV exports. If `--full-report` is used, the detailed
Markdown report should show compact table samples. If `--write-report` is used,
the same detailed Markdown report should also be written to:

```text
experiments/MS2_5/experiment_report.md
```

## Compact Terminal Report Shape

The default terminal report should fit a quick review:

```text
Milestone 2.5 Plan 2.5 Ingestion Examination

Run Context
  ticker:
  run timestamp:
  mode:
  SEC_USER_AGENT configured:
  report output:

Initial Setup Ingestion
  company existed before setup:
  setup status:
  SEC checked during setup:
  CIK:
  company name:

Already-Ingested Session Check
  company in system:
  update check needed this session:
  10-K check due:
  10-Q check due:
  SEC update check performed:
  SEC result:
  new filings ingested this session:
  next 10-K check date after session:
  next 10-Q check date after session:

Stored Rows After Session
  companies:
  filings:
  raw_xbrl_facts:
  financial_metrics:

Active Window After Session
  10-K:
  10-Q:

Base Metrics After Session

Source And Export Warnings

Full Evidence
  SQLite database:
  CSV exports:
  filing downloads:
  saved Markdown report:

Manual Judgment

More Detail
```

## Detailed Markdown Report Shape

The detailed Markdown report should focus on setup ingestion plus the
already-ingested session decision.

### Setup Ingestion

Purpose:

Show what the system creates when the chosen ticker is missing from the
isolated experiment database and the real Plan 2.5 ingestion workflow is used.

Evidence to present:

- run timestamp
- chosen ticker
- SEC mode
- `SEC_USER_AGENT` presence, without printing the value
- experiment database path
- report path
- CSV export directory
- company existed before setup: yes or no
- company registry row sample
- filings grouped by form type
- latest 10-K filing date
- latest 10-Q filing date
- `next_check_date_10k`
- `next_check_date_10q`
- raw fact count
- base metric count
- active-window counts for 10-K and 10-Q
- compact `financial_metrics` sample
- compact metric traceability sample

### Already-Ingested Session Check

Purpose:

Show what the workflow decides when the same ticker already exists in local
storage.

Evidence to present:

- company in local storage: yes or no
- 10-K and 10-Q refresh due flags
- next check dates before the session
- whether SEC was contacted
- whether new filing data was ingested
- newly ingested filing form, accession, filing date, fiscal period, and local
  path
- next check dates after the session
- stored row count deltas during the session

## Proposed Detailed Markdown Report Outline

```text
# Milestone 2.5 Live SEC Experiment Report

## Human Question

## Run Context
  ticker:
  run timestamp:
  database:
  report output:
  report:
  csv export directory:
  SEC_USER_AGENT configured:

## Setup Ingestion

### Company State

### Filing Inventory

### Raw Fact And Metric Counts

### Active Window

### Compact financial_metrics Sample

### Compact Traceability Sample

## Already-Ingested Session Check

### New Filings Ingested During Session

### Stored Row Deltas During Session

### Stored Evidence After Session

## Full Evidence Artifacts

## Manual Judgment
  This report presents evidence only. Review the report, database, and CSVs to
  decide whether the behavior matches the Milestone 2.5 design.
```

## Required Report Sections

1. Human question
2. Run context
3. Setup ingestion
4. Already-ingested session check
5. Company registry samples
6. Filing inventory samples
7. Raw fact and base metric counts
8. Active-window counts
9. Compact `financial_metrics` sample
10. Compact traceability sample
11. Full evidence artifact paths
12. Manual judgment note

## Implementation Guidance

- Reuse `src/ingestion/company.py` for company ingestion orchestration.
- Reuse `src/ingestion/refresh_policy.py` for update-check date logic.
- Reuse `src/processing/active_window.py` for active-window selection.
- Reuse `src/processing/base_metrics.py` for base metric mapping.
- Reuse repositories in `src/storage/` for all database reads and writes.
- Do not calculate derived indicators inside the experiment script.
- Do not duplicate SEC HTTP logic inside the experiment script.
- Do not define pass/fail labels inside the experiment script.
- Do not write to `stock_data.db`.
- Do not print secrets or the actual `SEC_USER_AGENT` value.
- Keep the default terminal output short and point to the SQLite database, CSV
  exports, filing downloads, and optional detailed report.
- Print compact terminal output by default.
- Print the detailed Markdown report only when `--full-report` is present.
- Write `experiment_report.md` only when `--write-report` is present.
- Store Decimal-compatible numeric text values as they come from the storage
  layer; do not convert report values through SQLite `REAL`.

## Storage To Inspect

The kept experiment database should contain the Milestone 2.5 tables:

```text
companies
filings
raw_xbrl_facts
financial_metrics
```

The report should also list the generated CSV exports under:

```text
data/exports/ms2_5/
```

## Edge Cases To Present

The experiment should present these conditions when they occur naturally:

- SEC is unavailable or returns a retryable error
- `SEC_USER_AGENT` is missing
- ticker cannot be resolved to a CIK
- no recent 10-K is available
- no recent 10-Q is available
- update-check date cannot be generated because latest filing date is missing
- base metrics are unavailable because concepts are missing or quality-flagged
- source raw fact ID is missing from a metric row
- duplicate or ambiguous facts are visible in raw fact quality flags

## Presentation Outcome

At the end of the experiment, the project owner should have enough evidence to
inspect:

- which ticker was used
- whether first-time setup created local state
- whether the company exists in local storage for an already-ingested session
- whether 10-K or 10-Q refresh checks are due
- whether SEC was contacted for update checking
- whether newer filing data was ingested during the session
- what 10-K and 10-Q refresh dates were generated
- which filing accessions are stored locally
- how many rows exist in each relevant table
- which rows are inside the active analysis window
- which base metrics were mapped
- which base metrics can be traced back to raw XBRL facts
- where to open the full SQLite database and CSV exports

The experiment should stop at presentation. The human reviewer decides whether
the observed behavior is acceptable.
