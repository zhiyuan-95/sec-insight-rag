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
  supporting evidence, classifier version, confidence, and label status
- target raw fact coverage for the assigned hard industry labels, including
  found, missing, and found-but-unmapped target facts
- alternate SEC/XBRL tags that map to the same internal business metric
- unknown SEC/XBRL concepts not currently mapped to base financial metrics
- Inline XBRL extension and dimensional fact coverage
- approved learned mappings with global, industry, or company scope
- missing exact target tags whose canonical metric is recovered through an
  approved alternate concept
- report-only LLM formula proposal diagnostics for unresolved target concepts
  after direct catalog and approved learned mapping, using period-scoped raw
  fact pools that include found targets, mapped base metrics, approved
  alternates, and unknown/unmapped raw facts, with target-compatible unit filtering,
  statement-first prompting, one representative context per target, and
  exact-context cache reuse
- saved Plan 2.5 target mapping report with compact run summary, target metric
  mapping status, and report-only formula proposal evidence; source rows remain
  available in SQLite and CSV exports

This experiment does not cover derived indicators, deterministic analytics,
retrieval indexes, Gemini calls, RAG answers, frontend behavior, durable
recovered metric storage, indicator use of recovered values, identity
inference, or pass/fail grading.

## Recommended Location

```text
experiments/MS2_5/
  experiment_proposal.md
  milestone25_live_sec_inspection.py
  milestone25_mapping_report_<TICKER>.md

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

The experiment should write a compact report to
`milestone25_mapping_report_<TICKER>.md` by default and should not print the
report body to the terminal.
`experiments/storage/experiment.db` should persist across runs and across
milestone experiments. The CSV exports should overwrite stable paths on each
run.
`--full-report` is accepted only as a compatibility flag; it should not append
the older full lineage appendix. `--write-report` is also accepted only as a
compatibility flag because the report is now always saved.

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

Compatibility detailed-flag run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER --full-report
```

Report-only LLM formula proposal run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER --full-report --formula-proposals
```

Use `--formula-proposal-target-limit N` for a capped live-provider smoke test.
The formula proposal panel evaluates one representative period context per
missing target to keep live provider calls bounded; the full eligible raw fact
pool is still shown in the report/export evidence.

Rules:

- exactly one ticker is accepted per run
- the Plan 2.5 target mapping report is saved to `milestone25_mapping_report_<TICKER>.md` by default
- the report body is not printed to the terminal
- `--full-report` is accepted for CLI compatibility but keeps the same fixed
  target mapping report shape
- `--write-report` is accepted for compatibility; the report is already saved
- both 10-K and 10-Q behavior are presented for that ticker
- normal runs do not delete `experiments/storage/experiment.db`; repeat runs
  should make already-ingested behavior visible
- hidden support options may override the database, report, filings, and
  export paths, but normal use should rely on the stable paths above

## Report And Evidence Artifacts

Main report output:

```text
experiments/MS2_5/milestone25_mapping_report_<TICKER>.md
```

Kept SQLite artifact:

```text
experiments/storage/experiment.db
```

Supporting CSV artifacts:

```text
data/exports/ms2_5/
```

The saved Markdown report should keep the fixed Plan 2.5 target mapping shape.
It should show the operational decision path first, then target metric mapping
status, then formula proposal evidence. It should not include model-similarity
mapping candidates, final recommendations, debt recovery diagnostics, annual
metric pivots, quarterly metric pivots, or the older full lineage appendix.

`--full-report` is accepted for CLI compatibility, but it should not change the
saved report into the old full appendix shape.

## Saved Target Mapping Report Shape

```text
# Plan 2.5 Target Mapping Report

## 0. Compact Summary
  ticker, CIK, timestamp, update-check status, SEC result,
  target metrics checked, mapped/missing target metrics, formula counts

## 1. Target Metrics Mapping Status
  one row per internal metric with mapping status, mapped concepts,
  approved alternates, and target XBRL concepts checked

## 2. Proposed Formulas For Formula Recommendations
  10-K proposed formula rows
  10-Q proposed formula rows

## 2A. LLM Formula Proposal Diagnostics Summary

## 2B. LLM Formula Proposal Diagnostics

## 2C. LLM Formula Proposal Component Evidence

## 2D. Eligible Formula Proposal Raw Fact Pool

```

## Required Report Sections

1. Compact summary
2. Target metric mapping status
3. Proposed formulas by filing form
4. Formula proposal diagnostics summary
5. Formula proposal diagnostics
6. Formula proposal component evidence
7. Eligible formula proposal raw fact pool

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
- Reuse `src/processing/metric_targets.py` for canonical target definitions and
  missing-target diagnostics.
- Read approved learned mappings from `xbrl_concept_mappings`; only approved
  learned mappings can supplement the source-controlled catalog.
- Do not generate model-similarity mapping candidates.
- Keep LLM formula proposal prompt text in `src/analyze/prompts.py`, provider
  calls in `src/analyze/xbrl_formula_proposals.py`, and period context
  construction, target-compatible unit filtering, exact-cache reuse, and deterministic validation in
  `src/processing/formula_proposals.py`. The provider panel is Gemini plus
  OpenAI `gpt-4.1-mini`.
- Treat LLM formula proposals as report-only evidence. Do not approve mappings,
  persist recovered values, or feed indicators from model confidence or model
  agreement. A model may also return a report-only zero-target decision when
  same-period raw facts provide affirmative evidence that the missing target
  may be zero; that decision is still review evidence and does not create a
  financial metric.
- Keep report-only debt recovery logic out of the saved Markdown report; use
  dedicated metric recovery tests for that behavior.
- Reuse repositories in `src/storage/` for all database reads and writes.
- Do not calculate derived indicators inside the experiment script.
- Do not persist recovered debt values or insert them into `financial_metrics`.
- Do not let indicator formulas consume recovered debt values in this
  experiment.
- Do not duplicate SEC HTTP logic inside the experiment script.
- Do not define pass/fail labels inside the experiment script.
- Do not write to `stock_data.db`.
- Do not delete or reset `experiments/storage/experiment.db` at startup.
- Do not print secrets or the actual `SEC_USER_AGENT` value.
- Save the fixed target mapping report to
  `milestone25_mapping_report_<TICKER>.md` by default without printing the
  report body to the terminal.
- Keep the saved Markdown report limited to compact summary, target metric
  mapping status, and formula proposal evidence.
- Accept `--full-report` as a compatibility flag; do not append the old full
  lineage report.
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

The generated CSV exports are written under:

```text
data/exports/ms2_5/
```

Numeric report values should use presentation-only abbreviations where useful:
`K`, `M`, `B`, and `T` represent thousands, millions, billions, and trillions.
Abbreviated values should use two decimal places when possible, and decimal
values below `1K` should be rounded to two decimal places. Stored SQLite values
and CSV exports should remain unmodified.

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
- where to inspect formula proposal evidence for unresolved targets
- where to open the full SQLite database and CSV exports

The experiment should stop at presentation. The human reviewer decides whether
the observed behavior is acceptable.
