# MS4 — Derived Financial Indicators

## Status

`active`

This file preserves the existing indicator design formerly called Milestone 3.
It was implemented without a grilling session and has not been redesigned
during the documentation migration. Its internal historical milestone wording
is retained until a future focused review.

Current evaluation found all 28 planned definitions, deterministic calculation,
lineage, SQLite persistence, ingestion integration, focused tests, and complete
annual report rows. The plan is not `completed` because its required quarterly
active-window report evidence is absent.

## Existing Accepted Design

Milestone 3 Design: Indicator Engine

Task Restatement
Build the deterministic derived indicator layer that sits on top of the base financial metrics created in Milestone 2.5. This milestone should calculate core financial indicators from `financial_metrics`, preserve formula and source traceability, store results locally, and make those results easy for later analytics and RAG layers to consume.

This milestone should not add LLM reasoning, Gemini calls, RAG synthesis, filing retrieval, benchmark comparison, frontend code, or broad API expansion unless the project scope changes.

Before Coding Checklist
- Restate the requested implementation scope.
- List formula edge cases before editing code.
- Identify expected changed files.
- Ask for confirmation before adding or changing the SQLite schema, because implementing this milestone likely requires a new `financial_indicators` table.
- Keep the change small and focused on indicators.

Why This Milestone Exists
Milestone 2.5 created the clean base metric layer:

```text
raw_xbrl_facts
  -> financial_metrics
```

That layer gives the project stable metric names such as `revenue`, `net_income`, `total_assets`, and `operating_cash_flow` while preserving traceability back to raw SEC/XBRL facts.

Milestone 3 adds the next deterministic layer:

```text
financial_metrics
  -> financial_indicators
```

The purpose is to calculate useful financial ratios, growth rates, margins, and cash-flow indicators without using an LLM. These indicators should become structured evidence for Milestone 4 analytics and later RAG explanations.

Core Scope
- Define an indicator formula registry for the current target catalog.
- Calculate supported indicators from base metrics only.
- Add only the narrow base-metric mappings needed by the target catalog.
- Treat `free_cash_flow` as a derived indicator, not a raw fact or base metric.
- Use `Decimal` for calculations.
- Store formulas, formula versions, calculated values, and source references.
- Preserve links back to source `financial_metrics` rows and underlying raw XBRL fact IDs.
- Default normal reads to the active analysis window.
- Verify behavior with the Milestone 3 experiment workflow unless the project testing policy changes.
- Update `docs/structure.md` when source modules, storage tables, metric mappings, or verification workflows change.

Out Of Scope
- Do not use Gemini or any other LLM for calculations.
- Do not run deterministic financial analysis beyond calculating indicators.
- Do not add benchmark or peer comparison logic.
- Do not build retrieval indexes or filing chunking.
- Do not add frontend code.
- Do not introduce a new LLM provider or model.
- Do not calculate unsupported indicators from unreliable or missing inputs.
- Do not modify raw data files.

Important Edge Cases
- Missing required base metrics.
- A required denominator is zero.
- Prior-period value is missing for growth calculations.
- Prior-period value is zero for growth calculations.
- Prior comparable fiscal period is missing for year-over-year indicators.
- Units do not match across source metrics.
- Annual and quarterly periods are accidentally mixed.
- Balance sheet facts are instant values while income statement and cash-flow facts are duration values.
- Return, turnover, and cash-conversion-cycle formulas need average balance-sheet values from current and prior instant periods.
- Cash-flow concepts may use negative or positive sign conventions.
- Capital expenditures may be reported as a positive cash outflow concept.
- Net income may be negative, making cash conversion interpretation tricky.
- EBITDA may be zero or negative, making net debt to EBITDA not meaningful.
- Interest expense may be reported as a negative value, so coverage should use absolute interest expense.
- EPS and share-count units must not be mixed with currency units.
- Cash conversion cycle requires period day counts from available start and end dates.
- Derived-on-derived formulas such as free cash flow margin and free cash flow growth must preserve all underlying source metrics.
- Multiple raw concepts may map to the same base metric.
- Multiple filings may contain values for the same metric and period.
- Inactive-window metrics should not be used by default.
- A calculated indicator should remain traceable even when it uses multiple base metrics.
- Skipped indicators should expose a reason rather than failing silently.

Likely Files Changed During Implementation
- `src/processing/base_metrics.py`
- `src/processing/concepts.py`
- `src/indicators/__init__.py`
- `src/indicators/formulas.py`
- `src/indicators/models.py`
- `src/indicators/engine.py`
- `src/storage/database.py`
- `src/storage/indicators_repository.py`
- `src/storage/__init__.py`
- `src/ingestion/company.py`
- `experiments/MS4/indicator_engine.py`
- `docs/structure.md`

Core Data Flow

```text
SEC companyfacts
  |
  v
raw_xbrl_facts
  |
  v
financial_metrics
  |
  v
financial_indicators
```

More concrete version:

```text
financial_metrics
  income_statement.revenue
  income_statement.cost_of_revenue
  income_statement.gross_profit
  income_statement.operating_income
  income_statement.net_income
  income_statement.research_and_development_expense
  income_statement.selling_general_and_administrative_expense
  income_statement.interest_expense
  income_statement.diluted_eps
  balance_sheet.total_assets
  balance_sheet.current_assets
  balance_sheet.current_liabilities
  balance_sheet.cash_and_equivalents
  balance_sheet.short_term_investments
  balance_sheet.accounts_receivable
  balance_sheet.inventory
  balance_sheet.accounts_payable
  balance_sheet.approved_debt_components
  balance_sheet.shareholders_equity
  shares.weighted_average_diluted_shares
  cash_flow_statement.operating_cash_flow
  cash_flow_statement.capital_expenditure
  cash_flow_statement.depreciation_and_amortization
        |
        v
financial_indicators
  revenue_growth_yoy
  operating_income_growth_yoy
  diluted_eps_growth_yoy
  free_cash_flow_growth_yoy
  gross_margin
  operating_margin
  net_margin
  rd_intensity
  sga_intensity
  cost_of_revenue_ratio
  return_on_assets
  return_on_equity
  asset_turnover
  operating_cash_flow_margin
  free_cash_flow
  free_cash_flow_margin
  cash_earnings_conversion
  capex_intensity
  current_ratio
  quick_ratio
  debt_to_equity
  net_debt_to_ebitda
  interest_coverage
  days_sales_outstanding
  days_inventory_outstanding
  days_payable_outstanding
  cash_conversion_cycle
  share_dilution_rate
```

Initial Indicator Catalog

Growth indicators

Revenue growth YoY
- Name: `revenue_growth_yoy`
- Formula: `(revenue_t - revenue_t_minus_1) / abs(revenue_t_minus_1)`
- Required metrics: current `revenue`, prior comparable `revenue`
- Period type: duration
- Output unit: ratio
- Skip when prior comparable revenue is missing or zero.

Operating income growth YoY
- Name: `operating_income_growth_yoy`
- Formula: `(operating_income_t - operating_income_t_minus_1) / abs(operating_income_t_minus_1)`
- Required metrics: current `operating_income`, prior comparable `operating_income`
- Period type: duration
- Output unit: ratio
- Skip when prior comparable operating income is missing or zero.

Diluted EPS growth YoY
- Name: `diluted_eps_growth_yoy`
- Formula: `(diluted_eps_t - diluted_eps_t_minus_1) / abs(diluted_eps_t_minus_1)`
- Required metrics: current `diluted_eps`, prior comparable `diluted_eps`
- Period type: duration
- Output unit: ratio
- Skip when diluted EPS is not mapped, prior comparable diluted EPS is missing, or prior comparable diluted EPS is zero.

Free cash flow growth YoY
- Name: `free_cash_flow_growth_yoy`
- Formula: `(free_cash_flow_t - free_cash_flow_t_minus_1) / abs(free_cash_flow_t_minus_1)`
- Required metrics: current and prior comparable `operating_cash_flow`, current and prior comparable `capital_expenditure`
- Period type: duration
- Output unit: ratio
- Skip when current or prior comparable free cash flow cannot be calculated, source units do not match, or prior comparable free cash flow is zero.

Margins and cost structure

Gross margin
- Name: `gross_margin`
- Formula: `gross_profit / revenue`
- Required metrics: `gross_profit`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when revenue is missing or zero.

Operating margin
- Name: `operating_margin`
- Formula: `operating_income / revenue`
- Required metrics: `operating_income`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when revenue is missing or zero.

Net margin
- Name: `net_margin`
- Formula: `net_income / revenue`
- Required metrics: `net_income`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when revenue is missing or zero.

R&D intensity
- Name: `rd_intensity`
- Formula: `research_and_development_expense / revenue`
- Required metrics: `research_and_development_expense`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when R&D expense is not mapped, revenue is missing, or revenue is zero.

SG&A intensity
- Name: `sga_intensity`
- Formula: `selling_general_and_administrative_expense / revenue`
- Required metrics: `selling_general_and_administrative_expense`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when SG&A expense is not mapped, revenue is missing, or revenue is zero.

Cost of revenue ratio
- Name: `cost_of_revenue_ratio`
- Formula: `cost_of_revenue / revenue`
- Required metrics: `cost_of_revenue`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when cost of revenue is missing, revenue is missing, or revenue is zero.

Returns

Return on assets
- Name: `return_on_assets`
- Formula: `net_income / average_total_assets`
- Required metrics: `net_income`, current `total_assets`, prior comparable `total_assets`
- Period type: mixed duration and instant
- Output unit: ratio
- Skip when net income is missing, either total assets value is missing, or average total assets is zero.

Return on equity
- Name: `return_on_equity`
- Formula: `net_income / average_shareholders_equity`
- Required metrics: `net_income`, current `shareholders_equity`, prior comparable `shareholders_equity`
- Period type: mixed duration and instant
- Output unit: ratio
- Skip when net income is missing, either shareholders equity value is missing, or average shareholders equity is zero.

Asset turnover
- Name: `asset_turnover`
- Formula: `revenue / average_total_assets`
- Required metrics: `revenue`, current `total_assets`, prior comparable `total_assets`
- Period type: mixed duration and instant
- Output unit: ratio
- Skip when revenue is missing, either total assets value is missing, or average total assets is zero.

Cash generation

Operating cash flow margin
- Name: `operating_cash_flow_margin`
- Formula: `operating_cash_flow / revenue`
- Required metrics: `operating_cash_flow`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when operating cash flow is missing, revenue is missing, or revenue is zero.

Free cash flow
- Name: `free_cash_flow`
- Formula: `operating_cash_flow - abs(capital_expenditure)`
- Required metrics: `operating_cash_flow`, `capital_expenditure`
- Period type: duration
- Output unit: same currency unit as source metrics
- Storage target: `financial_indicators`
- Skip when source units do not match.

Free cash flow margin
- Name: `free_cash_flow_margin`
- Formula: `free_cash_flow / revenue`
- Required metrics: `operating_cash_flow`, `capital_expenditure`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when free cash flow cannot be calculated, source units do not match, revenue is missing, or revenue is zero.

Cash earnings conversion
- Name: `cash_earnings_conversion`
- Formula: `operating_cash_flow / net_income`
- Required metrics: `operating_cash_flow`, `net_income`
- Period type: duration
- Output unit: ratio
- Skip when operating cash flow is missing, net income is missing, or net income is zero.

Capital expenditure intensity
- Name: `capex_intensity`
- Formula: `abs(capital_expenditure) / revenue`
- Required metrics: `capital_expenditure`, `revenue`
- Period type: duration
- Output unit: ratio
- Skip when capital expenditure is missing, revenue is missing, revenue is zero, or units do not match.

Liquidity and leverage

Current ratio
- Name: `current_ratio`
- Formula: `current_assets / current_liabilities`
- Required metrics: `current_assets`, `current_liabilities`
- Period type: instant
- Output unit: ratio
- Skip when current assets are missing, current liabilities are missing, or current liabilities are zero.

Quick ratio
- Name: `quick_ratio`
- Formula: `(cash_and_equivalents + short_term_investments + accounts_receivable) / current_liabilities`
- Required metrics: `cash_and_equivalents`, `short_term_investments`, `accounts_receivable`, `current_liabilities`
- Period type: instant
- Output unit: ratio
- Skip when any required metric is not mapped, units do not match, current liabilities are missing, or current liabilities are zero.

Debt to equity
- Name: `debt_to_equity`
- Formula: `total_debt / shareholders_equity`
- Required metrics: approved debt component metrics sufficient to calculate `total_debt`, `shareholders_equity`
- Period type: instant
- Output unit: ratio
- Skip when total debt is not mapped, shareholders equity is missing, or shareholders equity is zero.

Net debt to EBITDA
- Name: `net_debt_to_ebitda`
- Formula: `(total_debt - cash_and_equivalents - short_term_investments) / (operating_income + depreciation_and_amortization)`
- Required metrics: approved debt component metrics sufficient to calculate `total_debt`, `cash_and_equivalents`, `short_term_investments`, `operating_income`, `depreciation_and_amortization`
- Period type: mixed instant and duration
- Output unit: ratio
- Skip when any required metric is not mapped, units do not match, or EBITDA is zero or negative.

Interest coverage
- Name: `interest_coverage`
- Formula: `operating_income / abs(interest_expense)`
- Required metrics: `operating_income`, `interest_expense`
- Period type: duration
- Output unit: ratio
- Skip when interest expense is not mapped, interest expense is zero, or units do not match.

Operating efficiency and shareholders

Days sales outstanding
- Name: `days_sales_outstanding`
- Formula: `(average_accounts_receivable / revenue) * period_days`
- Required metrics: current `accounts_receivable`, prior comparable `accounts_receivable`, `revenue`
- Period type: mixed duration and instant
- Output unit: days
- Skip when accounts receivable is not mapped, prior comparable accounts receivable is missing, revenue is missing or zero, or period dates are missing.

Days inventory outstanding
- Name: `days_inventory_outstanding`
- Formula: `(average_inventory / cost_of_revenue) * period_days`
- Required metrics: current `inventory`, prior comparable `inventory`, `cost_of_revenue`
- Period type: mixed duration and instant
- Output unit: days
- Skip when inventory is not mapped, prior comparable inventory is missing, cost of revenue is missing or zero, or period dates are missing.

Days payable outstanding
- Name: `days_payable_outstanding`
- Formula: `(average_accounts_payable / cost_of_revenue) * period_days`
- Required metrics: current `accounts_payable`, prior comparable `accounts_payable`, `cost_of_revenue`
- Period type: mixed duration and instant
- Output unit: days
- Skip when accounts payable is not mapped, prior comparable accounts payable is missing, cost of revenue is missing or zero, or period dates are missing.

Cash conversion cycle
- Name: `cash_conversion_cycle`
- Formula: `days_sales_outstanding + days_inventory_outstanding - days_payable_outstanding`
- Required metrics: all metrics required by `days_sales_outstanding`, `days_inventory_outstanding`, and `days_payable_outstanding`
- Period type: mixed duration and instant
- Output unit: days
- Skip when any component cannot be calculated.

Share dilution rate
- Name: `share_dilution_rate`
- Formula: `(weighted_average_diluted_shares_t - weighted_average_diluted_shares_t_minus_1) / abs(weighted_average_diluted_shares_t_minus_1)`
- Required metrics: current `weighted_average_diluted_shares`, prior comparable `weighted_average_diluted_shares`
- Period type: duration
- Output unit: ratio
- Skip when diluted share count is not mapped, prior comparable diluted share count is missing, or prior comparable diluted share count is zero.

Base Metric Mapping Requirements

The indicator engine should calculate from `financial_metrics`, not directly from raw XBRL facts. To support the target catalog, implementation should add only the required base metric mappings that are missing.

Do not add `free_cash_flow` to the base metric mappings. It should be calculated by the indicator engine from `operating_cash_flow` and `capital_expenditure`, then stored as a derived indicator in `financial_indicators`.

Already covered by the current base-metric layer:
- `revenue`
- `cost_of_revenue`
- `gross_profit`
- `operating_income`
- `net_income`
- `cash_and_equivalents`
- `total_assets`
- `current_assets`
- `current_liabilities`
- `shareholders_equity`
- `operating_cash_flow`
- `capital_expenditure`

Additional base metrics needed by the new target catalog:
- `research_and_development_expense`
- `selling_general_and_administrative_expense`
- `interest_expense`
- `diluted_eps`
- `short_term_investments`
- `accounts_receivable`
- `inventory`
- `accounts_payable`
- debt component metrics sufficient to calculate `total_debt`
- `depreciation_and_amortization`
- `weighted_average_diluted_shares`

Debt mapping should be conservative. Prefer an explicit, documented debt component policy over summing every debt-like concept, because companies may report overlapping current, noncurrent, lease, borrowing, and long-term debt concepts. The indicator engine may calculate `total_debt` as an intermediate value from approved component metrics, but should preserve the component source metric IDs.

Do not map broad or ambiguous concepts merely to force an indicator to calculate. If a required metric cannot be mapped cleanly, the indicator should be skipped with a clear reason.

Formula Rules
- All indicator calculations must be deterministic.
- Use `Decimal`, not float.
- Do not call Gemini or any LLM.
- Do not infer missing values.
- Do not mix units.
- Do not mix annual and quarterly periods.
- Do not mix instant and duration facts in one formula unless the formula explicitly allows it.
- For formulas that use averages, calculate the average from current and prior comparable instant values.
- For formulas that use derived components, expand source references to the underlying base metrics.
- For cash conversion cycle components, calculate `period_days` from source `start_date` and `end_date`; skip when either date is missing.
- Store a clear skip reason for expected invalid inputs.
- Raise explicit errors for programming mistakes or unsupported formula definitions.

Period Alignment Rules
Period identity should use:

```text
company_id
period_type
fiscal_year
fiscal_period
active-window status
```

For same-period indicators:

```text
gross_margin for FY 2025
  uses gross_profit FY 2025
  uses revenue FY 2025
```

For year-over-year indicators:

```text
revenue_growth_yoy for FY 2025
  uses revenue FY 2025
  uses revenue FY 2024

revenue_growth_yoy for Q2 2025
  uses revenue Q2 2025
  uses revenue Q2 2024
```

For average balance-sheet formulas:

```text
return_on_assets for FY 2025
  uses net_income FY 2025
  uses total_assets FY 2025
  uses total_assets FY 2024
```

For the current target catalog, names ending in `_yoy` should use prior comparable fiscal periods:
- FY 2025 vs FY 2024.
- Q2 2025 vs Q2 2024.

Do not calculate sequential quarter-over-quarter growth for `_yoy` indicators.

Source Traceability Rules
Every stored indicator should include:
- Indicator name.
- Formula name.
- Formula version.
- Calculated value.
- Output unit.
- Fiscal year and fiscal period.
- Source metric IDs.
- Source raw fact IDs when available.
- Source accession numbers.
- Active-window flag.
- Skip reason when the indicator cannot be calculated.

Derived inputs should not hide provenance:
- `free_cash_flow_margin` and `free_cash_flow_growth_yoy` should include the operating cash flow and capital expenditure source metrics used to calculate free cash flow.
- `net_debt_to_ebitda` should include debt, cash, short-term investments, operating income, and depreciation/amortization source metrics.
- `cash_conversion_cycle` should be stored separately from `days_sales_outstanding`, `days_inventory_outstanding`, and `days_payable_outstanding`, while still including the underlying source metrics for the component formulas.
- The first schema does not need `source_indicator_ids` if source metric IDs are expanded and preserved.

Traceability example:

```text
financial_indicators.net_margin FY 2025
  value = net_income / revenue
  source metrics:
    financial_metrics.net_income FY 2025
    financial_metrics.revenue FY 2025
  source facts:
    raw_xbrl_facts.id for NetIncomeLoss
    raw_xbrl_facts.id for RevenueFromContractWithCustomerExcludingAssessedTax
```

Proposed Storage Table
Implementation should confirm before changing schema. The likely new table is `financial_indicators`.

Recommended minimum shape:

```sql
CREATE TABLE financial_indicators (
    indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    indicator_name TEXT NOT NULL,
    formula_name TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    value_numeric TEXT,
    unit TEXT NOT NULL,
    period_type TEXT NOT NULL,
    fiscal_year INTEGER,
    fiscal_period TEXT,
    start_date TEXT,
    end_date TEXT,
    filing_date TEXT,
    source_metric_ids TEXT NOT NULL,
    source_raw_fact_ids TEXT NOT NULL,
    source_accession_numbers TEXT NOT NULL,
    is_active_window INTEGER NOT NULL DEFAULT 1,
    calculation_status TEXT NOT NULL,
    skip_reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (
        company_id,
        indicator_name,
        period_type,
        fiscal_year,
        fiscal_period,
        formula_version
    ),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);
```

Suggested indexes:

```sql
CREATE INDEX idx_financial_indicators_company_active
ON financial_indicators (company_id, is_active_window);

CREATE INDEX idx_financial_indicators_lookup
ON financial_indicators (company_id, indicator_name, fiscal_year, fiscal_period);
```

Store JSON lists as text for:
- `source_metric_ids`
- `source_raw_fact_ids`
- `source_accession_numbers`

This matches the repository pattern already used for serializing structured values.

Indicator Models
Recommended dataclasses:

```text
IndicatorDefinition
  indicator_name
  formula_name
  formula_version
  required_metric_names
  output_unit
  period_type

IndicatorResult
  company_id
  indicator_name
  formula_name
  formula_version
  value_numeric
  unit
  period_type
  fiscal_year
  fiscal_period
  start_date
  end_date
  filing_date
  source_metric_ids
  source_raw_fact_ids
  source_accession_numbers
  is_active_window
  calculation_status
  skip_reason
```

Possible calculation statuses:

```text
calculated
skipped
```

Potential skip reasons:

```text
missing_required_metric
zero_denominator
missing_prior_period
zero_prior_period
unit_mismatch
period_type_mismatch
ambiguous_metric_set
missing_period_dates
unsupported_period_comparison
non_positive_ebitda
unsupported_debt_mapping
```

Repository Design
Add `FinancialIndicatorRepository` with:

- `initialize()`
- `upsert_indicators(indicators: list[FinancialIndicator]) -> int`
- `list_indicators(company_id, indicator_names=None, active_only=True) -> list[FinancialIndicator]`
- Optional `delete_for_company(company_id)` only if recalculation needs a clean replacement policy.

The first implementation should prefer upsert over delete-and-insert.

Engine Design
Add an engine that accepts base metrics and returns indicator results:

```text
calculate_indicators(company_id, metrics, active_only=True)
  -> list[IndicatorResult]
```

Responsibilities:
- Group metrics by period.
- Choose one usable metric per metric name and period.
- Find prior comparable periods for `_yoy` and average-balance formulas.
- Calculate formula dependencies in a deterministic order, such as free cash flow before free cash flow margin.
- Apply formula definitions.
- Build source reference lists.
- Return calculated and skipped indicator results.

The engine should not:
- Read from SQLite directly.
- Write to SQLite directly.
- Fetch SEC data.
- Call Gemini.

This keeps calculation testable and lets storage remain separate.

Integration With Company Ingestion
After Milestone 3 is implemented, company ingestion can add one step after base metrics are stored:

```text
stored base metrics
  -> list active company metrics
  -> calculate indicators
  -> upsert financial_indicators
  -> include stored_indicator_count in CompanyIngestionResult
```

This keeps `src/ingestion/company.py` as orchestration only. Formula logic stays in `src/indicators/`, and persistence stays in `src/storage/`.

Experiment Output Contract

The Milestone 3 experiment should be ticker-driven. For each requested ticker, the report should use only the active accession window by default and should make that scope visible before showing indicator values.

The experiment should print:
- The ticker or tickers requested.
- The database path.
- The active accession window used for each ticker, including accession number, form type, fiscal year, fiscal period, filing date, and active-window flag.
- A yearly indicator table for all requested indicators.
- A quarterly indicator table for all requested indicators.
- A skipped-indicator table that explains missing cells from the yearly and quarterly tables.
- A source-traceability table or detail section that maps each calculated indicator value back to source metric IDs, raw fact IDs, and accession numbers.

Annual and quarterly indicator tables should be complete for the requested indicator catalog:
- Include every requested indicator as a column, even when the value cannot be calculated.
- Use one row per ticker and fiscal period.
- Keep annual rows separate from quarterly rows.
- Show calculated numeric values where available.
- Show a compact skipped marker where unavailable, with the detailed reason in the skipped-indicator table.
- Do not include metrics or indicators from inactive accessions unless the experiment is explicitly run with an override such as `--include-inactive`.

The default annual table should be limited to the latest active annual accession window. The default quarterly table should be limited to the latest active quarterly accession window. This should match the active-window policy from Milestone 2.5: latest 5 annual periods and latest 12 quarterly periods when available.

Verification Plan

This project does not currently maintain an automated `tests/` suite. Use manual verification through the Milestone 3 experiment workflow unless the project testing policy changes.

Formula behavior to inspect:
- Year-over-year growth calculates against the prior comparable fiscal period.
- Year-over-year growth skips missing prior periods and zero prior values.
- Margins and cost ratios calculate from same-period duration metrics.
- Return and turnover indicators use average balance-sheet values.
- Free cash flow handles positive capital expenditure as a cash outflow.
- Free cash flow based indicators preserve operating cash flow and capital expenditure source metrics.
- Cash earnings conversion skips zero net income.
- Net debt to EBITDA skips zero or negative EBITDA.
- Cash conversion cycle stores DSO, DIO, and DPO separately and then calculates CCC.

Engine behavior to inspect:
- Groups annual periods correctly.
- Groups quarterly periods correctly.
- Does not mix annual and quarterly periods.
- Does not use inactive metrics when active-only is true.
- Preserves source metric IDs.
- Preserves source raw fact IDs.
- Returns clear skip reasons.

Repository behavior to inspect:
- Round-trips Decimal values as text.
- Round-trips source references as JSON lists.
- Upserts by company, indicator, period, and formula version.
- Filters active-window indicators by default.

Integration behavior to inspect:
- Company ingestion stores base metrics and then stores indicators.
- `CompanyIngestionResult` reports stored indicator count.
- Indicators remain traceable back to source metrics and raw facts.
- The Milestone 3 experiment report shows active accession-window scope, complete yearly and quarterly indicator tables, skipped rows, formula versions, and source metric IDs.

Success Criteria
- The current target indicator catalog can be calculated when clean required base metrics exist.
- The engine uses deterministic formulas only.
- Formula definitions and formula versions are stored.
- Every calculated indicator includes source metric and raw fact references.
- Invalid calculations are skipped with explicit reasons.
- Annual and quarterly periods are not mixed incorrectly.
- Active-window filtering is respected by default.
- Manual Milestone 3 verification output includes yearly and quarterly tables for all requested indicators within the active accession window and explains skipped indicators.
- Company ingestion can persist indicators after base metrics are stored.
- `docs/structure.md` reflects the implemented indicator layer, new storage table, base-metric mapping changes, and verification workflow.

Suggested Implementation Order
1. Confirm schema change for `financial_indicators`.
2. Add narrowly required base-metric mappings for the target catalog.
3. Add indicator dataclasses and formula registry.
4. Add pure formula helpers.
5. Add indicator engine and period grouping logic.
6. Add SQLite schema and repository.
7. Wire indicator calculation into company ingestion.
8. Add or update the Milestone 3 experiment script.
9. Update `docs/structure.md`.
10. Run the Milestone 3 manual verification workflow.

Open Decisions Before Coding
- Whether skipped indicators should be persisted, or only returned from the engine.
- Whether formula versions should start as `v1` or use semantic versions such as `1.0.0`.
- Whether `free_cash_flow` should always use `abs(capital_expenditure)` or preserve reported sign conventions for specific SEC concepts.
- Which debt concepts should be accepted as debt components for `total_debt`.
- Whether quick ratio and net debt should require `short_term_investments`, or skip when that metric is unavailable.

## Deferred Indicator Extensions

These extensions are preserved as future scope. They are not part of the
current 28-indicator completion contract and require a future focused design
review before implementation.

General extensions:

- ROIC
- three-year and five-year CAGR
- accrual ratio
- stock-based compensation ratio
- dividend and repurchase indicators
- Altman Z-score
- Piotroski F-score
- Beneish M-score
- DuPont decomposition
- margin bridges
- working-capital contribution analysis

A universal indicator set is not appropriate for every industry. Candidate
sector modules are:

- Banks: net interest margin, efficiency ratio, return on average assets,
  return on average equity, loan-to-deposit ratio, nonperforming-loan ratio,
  net charge-off ratio, provision coverage, CET1 capital ratio, deposit growth,
  and loan growth. Current ratio, inventory turnover, and debt-to-EBITDA are
  generally inappropriate for banks.
- Insurance: premium growth, loss ratio, expense ratio, combined ratio,
  investment yield, reserve development, and return on equity.
- REITs: FFO, AFFO, FFO per share, AFFO payout ratio, occupancy rate,
  same-property NOI growth, and net debt-to-EBITDAre.
- SaaS: ARR growth, net revenue retention, gross retention, Rule of 40, sales
  efficiency, stock-based compensation to revenue, and FCF margin.
