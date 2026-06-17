# Milestone 3 Experiment Proposal: Indicator Engine

## Purpose

This experiment should let a human inspect deterministic derived indicators
after base metrics exist. The output should show what was calculated, which
formula was used, which periods were skipped, and which source metrics support
each result. For each requested ticker, the experiment should also show complete
yearly and quarterly indicator tables scoped to the active accession window.

## Human Question

When base metrics are available, what derived indicators did the system
calculate, what formulas were used, which periods were skipped, and which source
metrics support each result? For the ticker I requested, can I inspect yearly
and quarterly tables containing every requested indicator within the active
accession window?

## Milestone Scope

This experiment covers:

- reading base metrics from `financial_metrics`
- calculating derived indicators
- preserving formula names or versions
- preserving source metric references
- separating annual and quarterly calculations
- showing the active accession window used for the requested ticker
- printing complete yearly and quarterly indicator tables for the requested indicator catalog
- showing skipped calculations for missing inputs or invalid denominators

This experiment does not cover SEC ingestion, base metric mapping, financial
analytics, retrieval, Gemini calls, or RAG answers.

## Recommended Location

```text
experiments/MS3/
  experiment_proposal.md
  milestone3_indicator_engine.py
```

## Data Modes

Use `local` mode by default. Use `fixture` only if a stable indicator fixture is
added later.

## Input Cases

### Case 1: Normal Company With Enough Metrics

Command:

```text
python experiments/MS3/milestone3_indicator_engine.py --ticker AAPL --mode local
```

Purpose:

Show normal indicator calculation across annual and quarterly active-window
periods for the requested ticker.

### Case 2: Missing Denominator Or Required Metric

Purpose:

Show skipped calculations with explicit reasons.

### Case 3: Mixed Annual And Quarterly Periods

Purpose:

Show that annual and quarterly values are not mixed incorrectly and that both
tables stay scoped to active-window accessions.

### Case 4: Full Requested Indicator Catalog

Purpose:

Show every requested indicator in both yearly and quarterly tables, even when
some indicators are skipped because required inputs are unavailable.

## Proposed Terminal Report

```text
Milestone 3 Experiment: Indicator Engine

Human Question:
  Can I inspect calculated indicators, formulas, periods, skipped cases, and
  source metric traceability, including yearly and quarterly active-window
  tables for every requested indicator?

Run Context:
  mode: local
  ticker: AAPL
  database: stock_data.db
  active_window_only: true

Active Accession Window:
  ticker  accession_number      form  fiscal_year  fiscal_period  filing_date
  AAPL    0000320193-...        10-K  2025         FY             ...
  AAPL    0000320193-...        10-Q  2026         Q2             ...

Input Metric Coverage:
  metric_name          annual periods  quarterly periods
  revenue              5               12
  net_income           5               12
  total_assets         5               12
  operating_cash_flow  5               12

Indicator Summary:
  indicator        period type  periods calculated  skipped periods  formula version
  revenue_growth_yoy annual      4                   1                v1
  net_margin       annual       5                   0                v1
  current_ratio    quarterly    12                  0                v1

Yearly Indicator Table:
  ticker  fiscal_year  revenue_growth_yoy  gross_margin  free_cash_flow  ...
  AAPL    2025         ...                 ...           ...             ...
  AAPL    2024         skipped             ...           ...             ...

Quarterly Indicator Table:
  ticker  fiscal_year  fiscal_period  revenue_growth_yoy  gross_margin  free_cash_flow  ...
  AAPL    2026         Q2             ...                 ...           ...             ...
  AAPL    2026         Q1             skipped             ...           ...             ...

Formula Preview:
  indicator        formula
  revenue_growth_yoy (revenue_t - revenue_t_minus_1) / abs(revenue_t_minus_1)
  net_margin       net_income / revenue

Traceability Samples:
  id  ticker  indicator       period   value  formula_version  source_metric_ids
  1   AAPL    revenue_growth_yoy  2025 FY  ...    v1               ...
  2   AAPL    net_margin      2023 FY  ...    v1               ...

Skipped Indicator Cases:
  ticker  period   indicator      reason
  AAPL    2024 FY  revenue_growth_yoy  missing prior comparable period
  AAPL    2024 Q2  current_ratio       missing denominator

Source Traceability:
  ticker  period   indicator       source_metric_ids  source_raw_fact_ids  source_accession_numbers
  AAPL    2025 FY  free_cash_flow  ...                ...                  ...

Artifacts To Inspect:
  database table: financial_metrics
  database table: <indicator table when implemented>

Expected Outcome:
  A human can see the active accession window, yearly and quarterly indicator
  tables for the requested ticker, what was calculated, what was skipped, which
  formula was used, and whether each result is traceable back to source metrics.
```

## Required Printed Sections

1. Human question
2. Run context
3. Active accession window
4. Input metric coverage
5. Indicator summary
6. Yearly indicator table
7. Quarterly indicator table
8. Formula preview
9. Traceability samples
10. Skipped indicator cases
11. Source traceability
12. Artifacts to inspect
13. Expected outcome

## Implementation Guidance

- Use the indicator engine once it exists under `src/indicators/`.
- Do not compute indicators inside the experiment script.
- Do not use Gemini or any LLM for deterministic calculations.
- Use active-window metrics and active-window indicator rows by default.
- Keep annual and quarterly indicator tables separate.
- Include every requested indicator as a table column, even when the value is skipped.
- Represent skipped cells with a compact marker and print detailed reasons in the skipped-indicator section.
- Include ticker, fiscal year, fiscal period, and accession scope in the output so multi-ticker extension remains straightforward.
- Print formula names or versions so calculations are auditable.
- Print source metric IDs for each stored indicator row.

## Edge Cases To Show

- missing input metric
- missing prior period for growth
- zero denominator
- annual and quarterly periods present at the same time
- active and inactive accessions present at the same time
- unsupported metric combination

## Expected Outcome

Milestone 3 looks healthy when the printed report lets the project owner
answer:

- Which indicators were calculated?
- Which yearly periods were calculated?
- Which quarterly periods were calculated?
- Which periods were skipped and why?
- Which active-window accessions were used?
- What formula was used?
- Which source metrics support each indicator?
