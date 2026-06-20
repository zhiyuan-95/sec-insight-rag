# Milestone 2.5 Experiment Proposal: Plan 2.5 Ingestion Manual Examination

## Purpose

This experiment is the official manual examination harness for the new Plan 2.5
company ingestion workflow. It lets a human inspect what the actual
`ingest_company()` workflow creates, reuses, refreshes, and preserves for one
manually chosen company.

The experiment uses live SEC behavior and persistent isolated local storage. It
should not mutate the real project database.

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
            -> data lineage view for financial_metrics availability
```

The experiment should show whether a chosen ticker can be initialized through
the real ingestion workflow, then preserved in steady experiment storage so
later runs can inspect already-ingested behavior, local refresh decisions, SEC
check behavior, newly ingested filings, and next check dates.

## Human Question

For a company I choose, what does Plan 2.5 ingestion do during setup and during
later already-ingested sessions: local existence, refresh due status, SEC update
check, newly ingested filings, next check dates, and stored evidence?

## Milestone Scope

This experiment covers:

- one manually chosen ticker per run
- the actual `src.ingestion.ingest_company()` workflow
- live SEC company initialization through Plan 2.5 ingestion
- persistent isolated experiment storage
- first-time setup ingestion when the ticker is absent from experiment storage
- already-ingested inspection when the ticker is present from a prior run
- already-ingested session inspection after the current setup or reuse step
- company registry state
- filing inventory state
- normalized SEC companyfacts plus conditionally extracted Inline XBRL extension
  and dimensional facts in `raw_xbrl_facts`
- latest ingested 10-K and 10-Q filing dates
- next-check dates for 10-K and 10-Q refresh checks
- active analysis window state
- active filing evidence for the latest 5 fiscal years of 10-K data and latest
  12 quarters of 10-Q data
- base financial metric mapping
- metric-level data lineage summary for `financial_metrics`
- traceability from `financial_metrics` to `raw_xbrl_facts` and filings
- raw fact mapping coverage: raw facts downloaded/stored, mapped raw facts,
  unmapped raw facts, unknown raw concepts, and supported mapping catalog size
- persisted hard industry label assignment, including assignment source, reason,
  supporting evidence, classifier version, and label review status
- target raw fact coverage for the assigned hard industry labels, including
  found, missing, and found-but-unmapped target facts
- alternate SEC/XBRL tags that map to the same internal business metric
- unknown SEC/XBRL concepts not currently mapped to base financial metrics
- Inline XBRL extension and dimensional fact coverage
- semantic mapping candidates that require review before use
- approved learned mappings with global, industry, or company scope
- missing exact target tags whose canonical metric is recovered through an
  approved alternate concept
- saved compact report with appended annual and quarterly XBRL metric evidence,
  with source rows still available in SQLite and CSV exports

This experiment does not cover derived indicators, deterministic analytics,
retrieval indexes, Gemini calls, RAG answers, frontend behavior, or pass/fail
grading.

## Recommended Location

```text
experiments/MS2_5/
  experiment_proposal.md
  milestone25_live_sec_inspection.py
  experiment_report.md

experiments/storage/
  experiment.db
  filings/

data/exports/
  ms2_5/
    companies.csv
    filings.csv
    raw_xbrl_facts.csv
    financial_metrics.csv
    company_industry_labels.csv
    xbrl_concept_mappings.csv
    metric_traceability_sample.csv
```

The experiment should write a compact report to `experiment_report.md` by
default and should not print the report body to the terminal.
`experiments/storage/experiment.db` should persist across runs and across
milestone experiments. The CSV exports should overwrite stable paths on each
run.
The detailed Markdown report sections should be added to the saved report only
when the user asks for them with `--full-report`. `--write-report` is accepted
only as a compatibility flag because the report is now always saved.

## Data Mode

This experiment uses live SEC behavior and persistent isolated local storage.

```text
live
  Contacts SEC for the chosen ticker.
  Requires SEC_USER_AGENT.
  May observe different SEC data depending on the run date.

isolated local storage
  Writes to experiments/storage/experiment.db.
  Writes filing downloads to experiments/storage/filings/.
  Does not write to the real stock_data.db.
  Does not write filing downloads to the real data_store/filings/ path.
  Keeps the experiment database after and between runs for manual SQLite
  inspection.
```

The experiment should not use the real project database as its write target.
That keeps first-time ingestion, repeat-run reuse, refresh-date generation,
active-window selection, and filing evidence storage inspectable without
changing real local company state.

## Command

Default run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER
```

Compatibility saved report run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER --write-report
```

Detailed saved report run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER --full-report
```

Rules:

- exactly one ticker is accepted per run
- the compact summary is saved to `experiment_report.md` by default
- the report body is not printed to the terminal
- `--full-report` includes the detailed Markdown report in `experiment_report.md`
- `--write-report` is accepted for compatibility; the report is already saved
- both 10-K and 10-Q behavior are presented for that ticker
- normal runs do not delete `experiments/storage/experiment.db`; repeat runs
  should make already-ingested behavior visible
- hidden support options may override the database, report, filings, and
  export paths, but normal use should rely on the stable paths above

## Report And Evidence Artifacts

Main report output:

```text
experiments/MS2_5/experiment_report.md
```

Kept SQLite artifact:

```text
experiments/storage/experiment.db
```

Supporting CSV artifacts:

```text
data/exports/ms2_5/
```

Financial metric lineage section:

```text
experiments/MS2_5/experiment_report.md
```

The compact saved report should show the operational decision path first:
whether the company is local, whether an update check is due this session,
whether SEC was checked, whether new filing data was ingested, and the next
10-K/10-Q check dates after the session. It should then show source-controlled
hard industry label assignment and target raw fact coverage. The same
`experiment_report.md` should append the full financial metric lineage content,
including company industry labels, target raw fact coverage, raw fact mapping
coverage, alternate and unknown SEC/XBRL tag evidence, and two pivoted XBRL
metric tables: one annual table with fiscal years as columns and one quarterly
table with fiscal quarters as columns. Other full rows should remain available
in `experiments/storage/experiment.db` and CSV exports. If `--full-report` is
used, the saved report should also include detailed Markdown sections and
compact table samples.

## Compact Saved Report Shape

The default saved report should fit a quick review:

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

Company Industry Labels
  assigned labels:
  label status:
  assignment source:
  assignment reason:

Target Raw Fact Coverage
  target concepts checked:
  found_mapped:
  missing_target:
  found_unmapped:

Base Metrics After Session

Source And Export Warnings

More Detail
```

## Detailed Markdown Report Shape

The detailed Markdown report should focus on setup ingestion plus the
already-ingested session decision.

### Setup Ingestion

Purpose:

Show what the system creates when the chosen ticker is missing from the
persistent isolated experiment database, and what it reuses when the ticker is
already present from an earlier experiment run.

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
- raw fact mapping coverage summary
- company industry label assignment and supporting evidence
- target raw fact coverage, including found, missing, and found-but-unmapped
  target concepts
- alternate SEC/XBRL tags for the same business metric
- unknown SEC/XBRL concepts not mapped into `financial_metrics`
- active-window counts for 10-K and 10-Q
- compact `financial_metrics` sample
- metric-level data lineage view showing raw XBRL concepts, system mappings,
  `financial_metrics` row counts, active-row counts, and inactive context rows
- compact metric traceability sample
- appended financial metric lineage section in `experiment_report.md`

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

### Raw Fact Mapping Coverage

### Company Industry Labels

### Target Raw Fact Coverage

### Found Target Facts

### Missing Target Facts

### Found But Unmapped Target Facts

### Active Window

### Financial Metric Data Lineage View

### Alternate SEC/XBRL Tags For Same Business Metric

### Compact financial_metrics Sample

### Compact Traceability Sample

## Already-Ingested Session Check

### New Filings Ingested During Session

### Stored Row Deltas During Session

### Stored Evidence After Session

```

## Required Report Sections

1. Human question
2. Run context
3. Setup ingestion
4. Already-ingested session check
5. Company registry samples
6. Filing inventory samples
7. Raw fact and base metric counts
8. Raw fact mapping coverage
9. Persisted company industry labels
10. Target raw fact coverage
11. Found, missing, and found-but-unmapped target facts
12. Active-window counts
13. Financial metric data lineage view
14. Inline XBRL extension coverage
15. Semantic mapping candidates awaiting review
16. Approved learned XBRL mappings
17. Alternate SEC/XBRL tags for the same business metric
18. Compact `financial_metrics` sample
19. Compact traceability sample
20. Annual XBRL financial metrics
21. Quarterly XBRL financial metrics
22. Unknown SEC/XBRL concepts not mapped to base financial metrics
23. Full evidence artifact paths

## Implementation Guidance

- Reuse `src/ingestion/company.py` for company ingestion orchestration.
- Reuse `src/ingestion/refresh_policy.py` for update-check date logic.
- Reuse `src/processing/active_window.py` for active-window selection.
- Reuse `src/processing/base_metrics.py` for base metric mapping.
- Reuse `src/processing/company_industry_labels.py` for explicit hard industry
  label assignments. Do not infer labels silently from observed raw facts.
- Reuse `src/processing/mapping_catalog.py` for approved mapping candidates and
  target raw fact coverage.
- Reuse `src/ingestion/inline_xbrl.py` and Arelle for active filing extension
  taxonomy loading; keep normalization in `src/processing/inline_xbrl.py`.
- Reuse `src/processing/semantic_mapping.py` only to generate review candidates.
- Read approved learned mappings from `xbrl_concept_mappings`; never treat a
  semantic candidate as an approved base metric mapping.
- Reuse repositories in `src/storage/` for all database reads and writes.
- Do not calculate derived indicators inside the experiment script.
- Do not duplicate SEC HTTP logic inside the experiment script.
- Do not define pass/fail labels inside the experiment script.
- Do not write to `stock_data.db`.
- Do not delete or reset `experiments/storage/experiment.db` at startup.
- Do not print secrets or the actual `SEC_USER_AGENT` value.
- Keep the default saved report compact and point to the SQLite database, CSV
  exports, filing downloads, and optional detailed sections.
- Append the financial metric data lineage view to `experiment_report.md`.
- Save the compact report to `experiment_report.md` by default without printing
  the report body to the terminal.
- Include the detailed Markdown report in `experiment_report.md` only when
  `--full-report` is present.
- Accept `--write-report` as a compatibility flag, not as a separate output
  mode.
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

The lineage text section should include two pivoted XBRL metric tables:

- Annual XBRL Financial Metrics: `metric_name`, `statement_type`, then one
  column per fiscal year.
- Quarterly XBRL Financial Metrics: `metric_name`, `statement_type`, then one
  column per fiscal quarter.

Each table should show the stored financial metric values in period columns.
Table cells should be padded to the column width so headers and values align in
the text report.
Numeric report values should use presentation-only abbreviations where useful:
`K`, `M`, `B`, and `T` represent thousands, millions, billions, and trillions.
Abbreviated values should use two decimal places when possible, and decimal
values below `1K` should be rounded to two decimal places. Stored SQLite values
and CSV exports should remain unmodified.
When multiple distinct values remain for one metric-period cell, the report
should keep them visible in the cell instead of silently dropping them.
The lineage text section should also highlight raw fact mapping coverage,
persisted hard industry labels, target raw fact coverage, Inline XBRL extension
coverage, semantic candidates, approved learned mappings, observed alternate
tags, and unknown concepts. Unknown concepts should appear after the quarterly
XBRL metric table, and Full Evidence paths should appear after the XBRL metric
tables.

## Edge Cases To Present

The experiment should present these conditions when they occur naturally:

- SEC is unavailable or returns a retryable error
- `SEC_USER_AGENT` is missing
- ticker cannot be resolved to a CIK
- no recent 10-K is available
- no recent 10-Q is available
- update-check date cannot be generated because latest filing date is missing
- base metrics are unavailable because concepts are missing or quality-flagged
- a company does not yet have a source-controlled hard industry label assignment
- a mapped raw concept has no usable `financial_metrics` rows for the active
  window
- source raw fact ID is missing from a metric row
- duplicate or ambiguous facts are visible in raw fact quality flags

## Presentation Outcome

At the end of the experiment, the project owner should have enough evidence to
inspect:

- which ticker was used
- whether first-time setup created local state or a repeat run reused it
- whether the company exists in local storage for an already-ingested session
- whether 10-K or 10-Q refresh checks are due
- whether SEC was contacted for update checking
- whether newer filing data was ingested during the session
- what 10-K and 10-Q refresh dates were generated
- which filing accessions are stored locally
- how many rows exist in each relevant table
- which rows are inside the active analysis window
- which base metrics were mapped
- how raw XBRL concepts map into available `financial_metrics`
- which hard industry labels are assigned and why
- which target raw facts were expected, found, missing, or found but unmapped
- which base metrics can be traced back to raw XBRL facts
- where to inspect annual and quarterly XBRL metric evidence
- where to open the full SQLite database and CSV exports

The experiment should stop at presentation. The human reviewer decides whether
the observed behavior is acceptable.
