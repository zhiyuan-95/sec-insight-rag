# Milestone 2.5 Experiment Proposal: Company Registry, Update Checks, And Base Metrics

## Purpose

This experiment should let a human inspect the behavior added after raw
SEC/XBRL ingestion: company registry state, existing-company versus new-company
behavior, 10-K and 10-Q update-check dates, active filing windows, and base
financial metrics.

The most important part is comparing cases. A human should be able to try one
company already in the system and one company not yet in the system, then see
what changed.

## Human Question

How does the system behave when the target company is already in local storage
versus when it is not, and can I inspect the generated 10-K and 10-Q
`update_check_date` values, active filing window, and base metrics?

## Milestone Scope

This experiment covers:

- company registry lookup and upsert behavior
- existing-company and new-company branch behavior
- repeated run behavior after a new company is created
- 10-K and 10-Q latest filing dates
- 10-K and 10-Q update-check dates
- filing inventory persistence
- active analysis window selection
- base financial metric mapping
- source raw fact traceability for base metrics

This experiment does not cover derived indicators, deterministic analytics,
retrieval, Gemini calls, or RAG answers.

## Recommended Location

```text
experiments/MS2_5/
  experiment_proposal.md
  milestone25_company_registry_metrics.py
```

## Data Modes

The experiment should support:

```text
local
  Uses stock_data.db and data_store/filings/.
  Best for inspecting current project state.

live
  Contacts SEC if the company needs ingestion or refresh.
  Must require SEC_USER_AGENT.
```

Default mode should be `local` if enough local data exists. Live behavior should
be explicit.

## Input Cases

### Case 1: Existing Company Already Stored Locally

Command:

```text
python experiments/MS2_5/milestone25_company_registry_metrics.py --existing-ticker AAPL --new-ticker MSFT --mode local
```

Purpose:

Show the reuse or refresh path for a company already in the local registry.

Expected human inspection:

- the existing ticker is marked `existed before run: yes`
- company registry dates are printed
- filing inventory is grouped by 10-K and 10-Q
- update-check dates are visible

### Case 2: New Company Not Stored Locally

Use the same command with a ticker not currently present in `companies`.

Purpose:

Show first-time creation behavior.

Expected human inspection:

- the new ticker is marked `existed before run: no`
- the new ticker is marked `exists after run: yes`
- local filing paths and metric rows are visible after ingestion

### Case 3: Repeated Run For The New Company

Run the same command again.

Purpose:

Show that the new company now follows the existing-company behavior path.

Expected human inspection:

- the repeated ticker is marked `existed before run: yes`
- action observed is reuse or refresh, not first-time creation

## Proposed Terminal Report

```text
Milestone 2.5 Experiment: Company Registry, Update Checks, And Base Metrics

Human Question:
  Can I inspect existing-company and new-company behavior, 10-K/10-Q
  update_check_date values, active windows, and base metric traceability?

Run Context:
  mode: local
  existing ticker case: AAPL
  new ticker case: MSFT
  database: stock_data.db
  filings directory: data_store/filings

Case Summary:
  case          ticker   existed before run   exists after run   action observed
  existing      AAPL     yes                  yes                reused/refreshed
  new           MSFT     no                   yes                ingested/created
  repeated new  MSFT     yes                  yes                reused/refreshed

Company Registry:
  ticker  cik         name             latest_10k_date  10-K update_check_date  latest_10q_date  10-Q update_check_date
  AAPL    0000320193  Apple Inc.       2023-11-03       2024-11-01              2024-02-02       2024-05-02
  MSFT    0000789019  Microsoft Corp.  ...              ...                     ...              ...

Database Columns Behind Update Checks:
  human label              database column
  10-K update_check_date   next_check_date_10k
  10-Q update_check_date   next_check_date_10q

Filing Inventory:
  ticker  form  active filings  latest filing date  update_check_date
  AAPL    10-K  5               ...                 ...
  AAPL    10-Q  12              ...                 ...
  MSFT    10-K  ...             ...                 ...
  MSFT    10-Q  ...             ...                 ...

Active Window:
  ticker  form  target window          active periods shown
  AAPL    10-K  latest 5 fiscal years  5
  AAPL    10-Q  latest 12 quarters     12
  MSFT    10-K  latest 5 fiscal years  ...
  MSFT    10-Q  latest 12 quarters     ...

Base Metrics:
  ticker  metric_name          period type  periods shown  source raw fact ids present
  AAPL    revenue              annual       5              yes
  AAPL    net_income           annual       5              yes
  AAPL    total_assets         annual       5              yes
  AAPL    operating_cash_flow  annual       5              yes

Top 5 financial_metrics Rows:
  id  ticker  metric_name  fiscal_year  fiscal_period  value  source_raw_fact_id
  1   AAPL    revenue      2023         FY             ...    ...
  2   AAPL    net_income   2023         FY             ...    ...
  3   AAPL    assets       2023         FY             ...    ...
  4   AAPL    revenue      2024         Q1             ...    ...
  5   AAPL    assets       2024         Q1             ...    ...

Artifacts To Inspect:
  database table: companies
  database table: filings
  database table: financial_metrics
  filing directory: data_store/filings

Expected Outcome:
  A human can compare existing-company and new-company behavior, verify that
  10-K and 10-Q update_check_date values were generated, confirm active-window
  counts, and inspect base metrics with source fact traceability.

Manual Judgment:
  Confirm that the registry, filing state, update-check dates, active window,
  and base metrics match the milestone design.
```

## Required Printed Sections

1. Human question
2. Run context
3. Case summary
4. Company registry
5. Database columns behind update checks
6. Filing inventory
7. Active window
8. Base metrics
9. Top five `financial_metrics` rows
10. Artifacts to inspect
11. Expected outcome
12. Manual judgment note

## Implementation Guidance

- Reuse `src/ingestion/company.py` for company ingestion orchestration.
- Reuse `src/ingestion/refresh_policy.py` for update-check dates.
- Reuse `src/processing/active_window.py` for active-window selection.
- Reuse `src/processing/base_metrics.py` for base metric mapping.
- Reuse repositories in `src/storage/` for all database reads and writes.
- Do not calculate base metrics or update-check dates inside the experiment
  script.
- Label the human-facing `update_check_date` values while also printing the
  actual columns: `next_check_date_10k` and `next_check_date_10q`.

## Storage To Inspect

The main database artifacts are:

```text
companies
filings
financial_metrics
```

The file artifact is:

```text
data_store/filings/
```

## Edge Cases To Show

- existing ticker is not actually in storage before the run
- new ticker already exists because of prior local work
- no recent 10-K is available
- no recent 10-Q is available
- update-check date cannot be generated because latest filing date is missing
- base metrics are unavailable because required concepts are missing or flagged
- source raw fact ID is missing from a metric row

## Expected Outcome

Milestone 2.5 looks healthy when the printed report lets the project owner
answer:

- Which companies existed before the experiment?
- Which companies exist after the experiment?
- Did existing and new companies follow different code paths?
- Were 10-K and 10-Q update-check dates generated?
- Which database columns store those update-check dates?
- How many active annual and quarterly filings are in scope?
- Which base metrics were mapped?
- Are base metrics traceable to raw XBRL facts?
