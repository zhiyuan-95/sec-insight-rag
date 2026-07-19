# Milestone 3 Experiment Proposal: Indicator Engine

## Purpose

This experiment should let a human inspect deterministic derived indicators
after base metrics exist. The output should show what was calculated, which
formula was used, which periods were skipped, and which source metrics support
each result. For each requested ticker, the experiment should also show complete
yearly and quarterly indicator tables scoped to the active accession window,
using the separate period-appropriate catalogs defined in
`docs/indicator_catalog.md`.
When a formula needs a prior comparable period or prior balance-sheet value,
the calculation may use stored `financial_metrics` outside that active window
as supporting context, while still emitting only active-window indicator rows by
default.

## Human Question

When base metrics are available, what derived indicators did the system
calculate, what formulas were used, which periods were skipped, and which source
metrics support each result? For the ticker I requested, can I inspect yearly
and quarterly tables containing every requested indicator applicable to each
period basis within the active accession window?

## Milestone Scope

This experiment covers:

- reading base metrics from `financial_metrics`
- calculating derived indicators
- preserving formula names or versions
- preserving source metric references
- selecting and separating annual, discrete-quarter, and TTM calculations
- showing the active accession window used for the requested ticker
- using out-of-window stored metrics as prior-period context when an active-window indicator formula needs them
- exporting complete yearly and quarterly tables for their respective
  period-appropriate indicator catalogs
- showing period-inapplicable indicators explicitly without mislabeling them as
  missing-input calculation skips
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

Show normal indicator calculation across annual FY, discrete-quarter, and
quarter-end TTM active-window periods for the requested ticker. The command writes
`experiments/MS3/milestone3_indicator_report_AAPL.txt` and does not print the
report body in the terminal.

### Case 2: Missing Denominator Or Required Metric

Purpose:

Show skipped calculations with explicit reasons.

### Case 3: Mixed Annual And Quarterly Periods

Purpose:

Show that annual, year-to-date, discrete-quarter, derived-Q4, and TTM values are
not mixed incorrectly and that both tables stay scoped to active-window
accessions.

### Case 4: Period-Appropriate Requested Indicator Catalogs

Purpose:

Show every requested annual-eligible indicator in the yearly table and every
requested quarterly-eligible indicator in the quarterly table. Keep
period-inapplicable indicators visible in a catalog-applicability section, and
show selected indicators with unavailable inputs as skipped cells.

## Proposed Report File

```text
Milestone 3 Experiment: Indicator Engine

Human Question:
  Can I inspect calculated indicators, formulas, periods, skipped cases, and
  source metric traceability, including yearly and quarterly active-window
  tables for every period-applicable requested indicator?

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
  metric_name          annual FY  discrete quarter  YTD excluded  TTM ready
  revenue              ...        ...               ...           ...
  net_income           ...        ...               ...           ...
  total_assets         ...        ...               ...           ...
  operating_cash_flow  ...        ...               ...           ...

Indicator Period Applicability:
  industry    indicator                    yearly  quarterly  quarterly basis
  Common      revenue_growth_yoy           yes     yes        discrete-quarter YoY
  Common      return_on_assets             yes     no         annual FY only
  Common      return_on_assets_ttm         no      yes        TTM at quarter end
  Common      revenue_growth_qoq           no      yes        prior discrete quarter
  Industrials ppe_turnover                 yes     no         annual FY only
  Industrials ppe_turnover_ttm             no      yes        TTM at quarter end
  Financials  net_interest_margin_annual   yes     no         banking sub-bundle
  Financials  net_interest_margin_quarterly_annualized
                                           no      yes        annualized discrete quarter

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
  ticker  indicator             2026 Q2  2026 Q1  2025 Q3  ...
  AAPL    revenue_growth_yoy    ...      skipped  ...      ...
  AAPL    revenue_growth_qoq    ...      skipped  ...      ...
  AAPL    gross_margin          ...      ...      ...      ...
  AAPL    free_cash_flow        ...      ...      ...      ...
  AAPL    return_on_assets_ttm  ...      ...      ...      ...

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
  tables for the requested ticker, which indicators apply to each period basis,
  what was calculated, what was skipped, which formula was used, and whether
  each result is traceable back to source metrics.
```

## Required Report Sections

1. Human question
2. Run context
3. Active accession window
4. Input metric coverage
5. Indicator period applicability
6. Indicator summary
7. Yearly indicator table
8. Quarterly indicator table
9. Formula preview
10. Traceability samples
11. Skipped indicator cases
12. Source traceability
13. Artifacts to inspect
14. Expected outcome

## Implementation Guidance

- Use the indicator engine once it exists under `src/indicators/`.
- Do not compute indicators inside the experiment script.
- Do not use Gemini or any LLM for deterministic calculations.
- Use active-window periods and active-window indicator rows by default, but allow stored out-of-window metrics as prior-period formula context.
- Use `docs/indicator_catalog.md` for common, industry, and period applicability.
- Keep annual FY and quarterly indicator tables separate and use their distinct
  selected indicator sets.
- Normalize 10-Q duration facts before calculating indicators: use discrete
  three-month values, not six- or nine-month YTD values, in quarterly cells.
- Derive a discrete cash-flow quarter by YTD differencing only when concepts,
  units, consolidation scope, and fiscal dates match, and preserve both sources.
- Do not show Q4 as a reported 10-Q period. Derive Q4 only from a traceable
  full-year less nine-month-YTD bridge when every compatibility check passes.
- Calculate quarterly TTM indicators only when four validated discrete quarters
  are available.
- Write the report as a `.txt` file under `experiments/MS3` by default and do not print the report body in the terminal.
- Present each period-applicable requested indicator as a table row and each
  fiscal period as a table column, even when the calculation is skipped.
- Show period-inapplicable indicators in the applicability section; do not label
  them as missing-input skips.
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
- both discrete-quarter and YTD facts present for the same fiscal quarter
- Q4 unavailable because no valid annual less nine-month-YTD bridge exists
- a TTM calculation with one missing discrete quarter
- a QoQ calculation that crosses a fiscal-year boundary
- active and inactive accessions present at the same time
- unsupported metric combination

## Expected Outcome

Milestone 3 looks healthy when the exported report lets the project owner
answer:

- Which indicators were calculated?
- Which yearly periods were calculated?
- Which quarterly periods were calculated?
- Which indicators were selected for each period basis, and which were not
  applicable?
- Were quarterly values reported discrete facts, deterministically derived from
  YTD facts, or TTM calculations?
- Which periods were skipped and why?
- Which active-window accessions were used?
- What formula was used?
- Which source metrics support each indicator?
