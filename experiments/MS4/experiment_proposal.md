# Milestone 4 Experiment Proposal: Deterministic Financial Data Analysis

## Purpose

This experiment should let a human inspect deterministic financial analysis
before any LLM explanation is generated. The report should show trends, period
comparisons, gaps, outliers, and chart-ready rows.

## Human Question

Can I inspect deterministic trend analysis, period comparisons, and chart-ready
data before any Gemini or RAG synthesis is generated?

## Milestone Scope

This experiment covers:

- deterministic trend analysis
- period-over-period comparisons
- gap and outlier notes
- chart-ready output rows
- clear separation from LLM-generated interpretation

This experiment does not cover SEC ingestion, indicator formula implementation,
retrieval, Gemini calls, or final RAG answers.

## Recommended Location

```text
experiments/MS4/
  experiment_proposal.md
  milestone4_financial_analytics.py
```

## Data Modes

Use `local` mode by default. Use `fixture` only if stable analytics fixtures are
added later.

## Input Cases

### Case 1: Normal Multi-Period Company History

Command:

```text
python experiments/MS4/milestone4_financial_analytics.py --ticker AAPL --mode local
```

Purpose:

Show normal trend and comparison behavior.

### Case 2: Missing Periods

Purpose:

Show gaps clearly instead of hiding them.

### Case 3: Obvious Outlier Or Decline

Purpose:

Show how deterministic analysis labels large changes.

## Proposed Terminal Report

```text
Milestone 4 Experiment: Deterministic Financial Data Analysis

Human Question:
  Can I inspect trend and comparison outputs before any Gemini synthesis?

Run Context:
  mode: local
  ticker: AAPL
  database: stock_data.db

Trend Summary:
  metric      periods analyzed  direction  latest value  change from prior period
  revenue    5 annual          up          ...           ...
  net_income 5 annual          down        ...           ...

Period Comparison:
  metric    current period  prior period  absolute change  percent change
  revenue   2023 FY         2022 FY       ...              ...

Gap And Outlier Notes:
  metric      period   observation
  revenue     2021 FY  missing prior period
  net_income  2022 FY  large decline

Chart-Ready Data Preview:
  metric    period    value
  revenue   2019 FY   ...
  revenue   2020 FY   ...
  revenue   2021 FY   ...

Artifacts To Inspect:
  source module: src/analytics/
  database table: financial_metrics
  database table: <indicator table when implemented>

Expected Outcome:
  A human can inspect deterministic trend direction, period comparisons, gaps,
  outliers, and chart-ready rows without any Gemini or RAG output.
```

## Required Printed Sections

1. Human question
2. Run context
3. Trend summary
4. Period comparison
5. Gap and outlier notes
6. Chart-ready data preview
7. Artifacts to inspect
8. Expected outcome

## Implementation Guidance

- Use deterministic analytics code under `src/analytics/`.
- Do not call Gemini.
- Do not ask an LLM to classify trends or compute comparisons.
- Use raw facts, base metrics, or indicators as inputs depending on the
  implemented analytics layer.
- Print chart-ready rows in a simple table shape.

## Edge Cases To Show

- missing periods
- one-period company history
- outlier movement
- negative values
- zero prior-period values for percent changes
- benchmark requested before benchmark data exists

## Expected Outcome

Milestone 4 looks healthy when the printed report lets the project owner
answer:

- What trends were detected?
- What changed between periods?
- Are missing periods visible?
- Are outliers visible?
- Can the output be plotted without reshaping?
- Is the analysis deterministic and separate from LLM interpretation?
