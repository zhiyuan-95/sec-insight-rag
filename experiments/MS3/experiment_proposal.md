# Milestone 3 Experiment Proposal: Indicator Engine

## Purpose

This experiment should let a human inspect deterministic derived indicators
after base metrics exist. The output should show what was calculated, which
formula was used, which periods were skipped, and which source metrics support
each result. For each requested ticker, the experiment should also show complete
yearly and quarterly indicator tables scoped to the active accession window.
When a formula needs a prior comparable period or prior balance-sheet value,
the calculation may use stored `financial_metrics` outside that active window
as supporting context, while still emitting only active-window indicator rows by
default.

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
- using out-of-window stored metrics as prior-period context when an active-window indicator formula needs them
- exporting complete yearly and quarterly indicator tables for the requested indicator catalog
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
periods for the requested ticker. The command writes
`experiments/MS3/milestone3_indicator_report_AAPL.txt` and does not print the
report body in the terminal.

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

## Proposed Report File

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
  report_file: experiments/MS3/milestone3_indicator_report_AAPL.txt

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
  indicator        period type  periods calculated  skipped periods  skip reasons              formula version
  revenue_growth_yoy annual      4                   1                missing_prior_period (1)  v1
  net_margin       annual       5                   0                                          v1
  current_ratio    quarterly    12                  0                                          v1

Yearly Indicator Table:
  ticker  indicator           2025  2024     2023  ...
  AAPL    revenue_growth_yoy  ...   skipped  ...   ...
  AAPL    gross_margin        ...   ...      ...   ...
  AAPL    free_cash_flow      ...   ...      ...   ...

Quarterly Indicator Table:
  ticker  indicator           2026 Q2  2026 Q1  2025 Q4  ...
  AAPL    revenue_growth_yoy  ...      skipped  ...      ...
  AAPL    gross_margin        ...      ...      ...      ...
  AAPL    free_cash_flow      ...      ...      ...      ...

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
  report file: experiments/MS3/milestone3_indicator_report_AAPL.txt
  database table: financial_metrics
  database table: financial_indicators

Expected Outcome:
  A human can see the active accession window, yearly and quarterly indicator
  tables for the requested ticker, what was calculated, what was skipped, which
  formula was used, and whether each result is traceable back to source metrics.
```

## Required Report Sections

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
- Use active-window periods and active-window indicator rows by default, but allow stored out-of-window metrics as prior-period formula context.
- Keep annual and quarterly indicator tables separate.
- Write the report as a `.txt` file under `experiments/MS3` by default and do not print the report body in the terminal.
- Present each requested indicator as a table row and each fiscal period as a table column, even when the value is skipped.
- Represent skipped cells with a compact marker, summarize skipped reason counts in the indicator summary, and include detailed per-period reasons in the skipped-indicator section.
- Round only when formatting presentation output; keep stored indicator values at full precision.
- Display growth, margins, returns, intensities, and conversion indicators as percentages, ratio indicators to two decimals, working-capital cycle indicators as one-decimal day counts, and free cash flow as compact currency.
- Include ticker, fiscal year, fiscal period, and accession scope in the output so multi-ticker extension remains straightforward.
- Include formula names or versions so calculations are auditable.
- Include source metric IDs for each stored indicator row.

## Edge Cases To Show

- missing input metric
- missing prior period for growth after checking stored out-of-window metrics
- zero denominator
- annual and quarterly periods present at the same time
- active and inactive accessions present at the same time
- unsupported metric combination

## Expected Outcome

Milestone 3 looks healthy when the exported report lets the project owner
answer:

- Which indicators were calculated?
- Which yearly periods were calculated?
- Which quarterly periods were calculated?
- Which periods were skipped and why?
- Which active-window accessions were used?
- What formula was used?
- Which source metrics support each indicator?
