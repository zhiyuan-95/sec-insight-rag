# Milestone 3 Experiment Proposal: Indicator Engine

## Purpose

This experiment should let a human inspect deterministic derived indicators
after base metrics exist. The output should show what was calculated, which
formula was used, which periods were skipped, and which source metrics support
each result.

## Human Question

When base metrics are available, what derived indicators did the system
calculate, what formulas were used, which periods were skipped, and which source
metrics support each result?

## Milestone Scope

This experiment covers:

- reading base metrics from `financial_metrics`
- calculating derived indicators
- preserving formula names or versions
- preserving source metric references
- separating annual and quarterly calculations
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

Show normal indicator calculation across annual and quarterly periods.

### Case 2: Missing Denominator Or Required Metric

Purpose:

Show skipped calculations with explicit reasons.

### Case 3: Mixed Annual And Quarterly Periods

Purpose:

Show that annual and quarterly values are not mixed incorrectly.

## Proposed Terminal Report

```text
Milestone 3 Experiment: Indicator Engine

Human Question:
  Can I inspect calculated indicators, formulas, periods, skipped cases, and
  source metric traceability?

Run Context:
  mode: local
  ticker: AAPL
  database: stock_data.db

Input Metric Coverage:
  metric_name          annual periods  quarterly periods
  revenue              5               12
  net_income           5               12
  total_assets         5               12
  operating_cash_flow  5               12

Indicator Summary:
  indicator        period type  periods calculated  skipped periods  formula version
  revenue_growth   annual       4                   1                v1
  net_margin       annual       5                   0                v1
  current_ratio    quarterly    12                  0                v1

Formula Preview:
  indicator        formula
  revenue_growth   (revenue_t / revenue_t_minus_1) - 1
  net_margin       net_income / revenue

Top 5 Indicator Rows:
  id  ticker  indicator       period   value  formula_version  source_metric_ids
  1   AAPL    revenue_growth  2023 FY  ...    v1               ...
  2   AAPL    net_margin      2023 FY  ...    v1               ...

Skipped Indicator Cases:
  indicator      period   reason
  current_ratio  2024 Q2  missing denominator

Artifacts To Inspect:
  database table: financial_metrics
  database table: <indicator table when implemented>

Expected Outcome:
  A human can see what was calculated, what was skipped, which formula was used,
  and whether each result is traceable back to source metrics.
```

## Required Printed Sections

1. Human question
2. Run context
3. Input metric coverage
4. Indicator summary
5. Formula preview
6. Top five indicator rows
7. Skipped indicator cases
8. Artifacts to inspect
9. Expected outcome

## Implementation Guidance

- Use the indicator engine once it exists under `src/indicators/`.
- Do not compute indicators inside the experiment script.
- Do not use Gemini or any LLM for deterministic calculations.
- Print formula names or versions so calculations are auditable.
- Print source metric IDs for each stored indicator row.

## Edge Cases To Show

- missing input metric
- missing prior period for growth
- zero denominator
- annual and quarterly periods present at the same time
- unsupported metric combination

## Expected Outcome

Milestone 3 looks healthy when the printed report lets the project owner
answer:

- Which indicators were calculated?
- Which periods were calculated?
- Which periods were skipped and why?
- What formula was used?
- Which source metrics support each indicator?
