# Common and Industry-Specific Financial Indicator Catalog

## Purpose

This document defines which derived financial indicators belong in the common
cross-industry catalog and which indicators should be selected only for
companies with particular hard industry labels.

The catalog prevents the system and its reports from implying that every
industry should be evaluated with the same indicator set. It is a design
contract for future industry-aware indicator selection. It does not claim that
all formulas in this document are implemented.

The current runtime still has one 28-indicator formula registry in
`src/indicators/formulas.py`. It calculates or skips those definitions without
selecting a different registry by industry. The status column in this document
distinguishes that implemented catalog from proposed specialized formulas.

## Catalog Terms

- **Common core indicator**: eligible for every hard industry label when the
  required normalized metrics are present and comparable. Common does not mean
  that a value must be forced for every company.
- **Industry-specific indicator**: selected only when the company has the named
  hard industry label and the formula's business-model qualification is met.
- **Input-qualified indicator**: selected only when the company reports the
  metric family required by the formula. This is especially important inside
  the broad `Financials` and `Real Estate` labels.
- **Annual FY indicator**: calculated from a full-fiscal-year duration and/or
  the corresponding fiscal-year-end instant facts.
- **Discrete-quarter indicator**: calculated from one fiscal quarter's duration
  and/or the corresponding quarter-end instant facts. A six- or nine-month
  year-to-date duration is not a discrete quarter.
- **TTM indicator**: calculated at a quarter end from the latest four validated
  discrete fiscal quarters for duration metrics and the appropriate instant
  balance-sheet facts.
- **Implemented**: the deterministic formula already exists in
  `src/indicators/formulas.py` and `src/indicators/engine.py`.
- **Proposed - catalog inputs exist**: the formula is not implemented, but its
  principal source metrics already appear in the common or industry target
  catalog in `src/processing/mapping_catalog.py`.
- **Proposed - additional inputs required**: the formula is not implemented and
  one or more normalized metric mappings must be added and reviewed first.
- **Proposed - quarterly normalization required**: the source metrics may exist,
  but the formula cannot be activated until discrete-quarter, derived-Q4, and
  TTM basis rules are implemented and traceable.
- **Not applicable**: the indicator is outside the selected common and industry
  bundles. This is different from **skipped**, which means the indicator was
  selected but could not be calculated from the available period evidence.

## Selection Rules

For a company with one or more approved hard industry labels:

```text
selected indicators
  = (common core
     + bundle for each assigned hard industry label
     + any satisfied input-qualified sub-bundles)
    intersected with the annual or quarterly period catalog
```

Apply these rules:

1. De-duplicate indicator names after taking the union of multiple industry
   bundles.
2. Do not give one indicator name different formulas in different industries.
   Use a distinct name when the economic definition changes.
3. Do not select an industry indicator merely because one raw concept happens
   to exist. The company must have the approved hard industry label.
4. Do not force a selected indicator when required metrics are missing,
   ambiguous, unit-incompatible, or not period-comparable. Store or report a
   deterministic skip reason.
5. Preserve source metric IDs, raw fact IDs, accession numbers, formula name,
   formula version, and the industry label that selected the indicator.
6. A multi-industry company receives the union of its approved bundles. For
   example, Tesla can receive the Consumer Discretionary, Industrials, and
   Energy bundles without calculating duplicate common indicators three times.
7. Reports should identify the common core, assigned labels, selected industry
   bundles, and indicators excluded as not applicable.
8. A filing form is an evidence source, not a sufficient measurement basis.
   Indicator selection must also use fiscal period, start date, end date, and
   whether a duration is annual, discrete-quarter, year-to-date, or TTM.

## Common Core

These indicators are the small cross-industry baseline. Specialized indicators
should lead the interpretation when a common ratio is structurally weak for an
industry, such as GAAP net margin for an equity REIT or generic revenue growth
for a bank.

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `revenue_growth_yoy` | `(revenue_t - revenue_t-1) / abs(revenue_t-1)` | Implemented | Use only when `revenue` is a comparable top-line measure. Prefer the relevant Financials or Real Estate growth measure when it better represents operations. |
| `diluted_eps_growth_yoy` | `(diluted_eps_t - diluted_eps_t-1) / abs(diluted_eps_t-1)` | Implemented | Skip when diluted EPS is missing or the prior comparable period is zero. |
| `net_margin` | `net_income / revenue` | Implemented | Keep as GAAP context; do not make it the primary operating measure for banks, insurers, or REITs. |
| `return_on_assets` | `net_income / average_total_assets` | Implemented | Requires current and prior comparable total assets. Interpretation differs for asset-intensive and financial companies. |
| `return_on_equity` | `net_income / average_shareholders_equity` | Implemented | Requires current and prior comparable equity. Do not compare across industries without a peer methodology. |
| `share_dilution_rate` | `(diluted_shares_t - diluted_shares_t-1) / abs(diluted_shares_t-1)` | Implemented | Use weighted-average diluted shares from comparable periods. |

## Annual and Quarterly Period Catalogs

### Decision

Do not use exactly the same indicator set for 10-K and 10-Q output. Maintain one
formula registry, then attach period applicability to each definition. The final
set for one company is the intersection of:

1. the common and assigned-industry bundles; and
2. the annual or quarterly period catalog.

This avoids duplicated formula implementations while preventing a quarterly
flow from being inserted into a formula whose denominator assumes a full year.

### Period Normalization Requirements

| Measurement basis | Evidence and calculation rule | Report destination |
| --- | --- | --- |
| Annual FY | Full-year duration facts and fiscal-year-end instant facts, normally sourced from the active 10-K accession. | Yearly table |
| Discrete quarter | Three-month duration facts and quarter-end instant facts from the active 10-Q accession. Q2 and Q3 year-to-date durations must not be treated as discrete quarters. | Quarterly table |
| Discrete quarterly cash flow | Q1 can use the three-month YTD amount. Q2 and Q3 operating cash flow and capex generally require deterministic differencing of current YTD less prior YTD when no discrete fact exists. | Quarterly table |
| Derived Q4 | Optional only when `full_year - nine_month_YTD` can be calculated from compatible units, concepts, consolidation scopes, and fiscal dates. Preserve both sources and label the value as derived from the 10-K bridge, not as a reported 10-Q value. | Quarterly history, never labeled as a 10-Q filing |
| TTM at quarter end | Sum four validated discrete quarters for each duration metric; use the current quarter-end instant and the appropriate prior balance for averages. Skip when any required quarter is unavailable. | Quarterly table with a `TTM` basis label |

The quarterly normalizer must prefer an explicitly reported discrete fact over a
derived value. It must not choose between three-month and year-to-date facts
merely by latest filing date or raw fact ID.

### Shared Annual and Quarterly Set

The following 24 implemented indicators can use the same formula in the annual
and discrete-quarter catalogs. A quarterly value still requires validated
discrete-quarter inputs, and a `_yoy` formula compares the quarter with the same
fiscal quarter in the prior year.

| Family | Indicators |
| --- | --- |
| Year-over-year growth | `revenue_growth_yoy`, `operating_income_growth_yoy`, `diluted_eps_growth_yoy`, `free_cash_flow_growth_yoy` |
| Margins and cost structure | `gross_margin`, `operating_margin`, `net_margin`, `rd_intensity`, `sga_intensity`, `cost_of_revenue_ratio` |
| Cash generation | `operating_cash_flow_margin`, `free_cash_flow`, `free_cash_flow_margin`, `cash_earnings_conversion`, `capex_intensity` |
| Quarter-end or year-end balance ratios | `current_ratio`, `quick_ratio`, `debt_to_equity` |
| Coverage | `interest_coverage` |
| Working capital | `days_sales_outstanding`, `days_inventory_outstanding`, `days_payable_outstanding`, `cash_conversion_cycle` |
| Shareholder impact | `share_dilution_rate` |

Margins, cash generation, coverage, and working-capital indicators can be more
seasonal in a quarter than in a full year. The report must label the basis and
must not compare an FY result directly with one discrete quarter.

### Annual-Only Names From the Current Registry

The current names below should be emitted for annual FY calculations. They
combine duration flows with average or point-in-time balances, or combine
point-in-time debt with an earnings denominator intended to represent a full
year.

| Annual indicator | Annual formula |
| --- | --- |
| `return_on_assets` | `annual_net_income / average_total_assets` |
| `return_on_equity` | `annual_net_income / average_shareholders_equity` |
| `asset_turnover` | `annual_revenue / average_total_assets` |
| `net_debt_to_ebitda` | `year_end_net_debt / annual_EBITDA` |

Do not place the raw three-month versions of these four names in the quarterly
table. A three-month numerator would produce a value on a different scale from
the annual indicator.

### Quarterly TTM Replacements

Use distinct names so the system never stores materially different period
definitions under one indicator name.

| Quarterly indicator | Formula | Status |
| --- | --- | --- |
| `return_on_assets_ttm` | `TTM_net_income / average(total_assets_at_quarter_end, total_assets_same_quarter_prior_year)` | Proposed - quarterly normalization required |
| `return_on_equity_ttm` | `TTM_net_income / average(equity_at_quarter_end, equity_same_quarter_prior_year)` | Proposed - quarterly normalization required |
| `asset_turnover_ttm` | `TTM_revenue / average(total_assets_at_quarter_end, total_assets_same_quarter_prior_year)` | Proposed - quarterly normalization required |
| `net_debt_to_ebitda_ttm` | `quarter_end_net_debt / TTM_EBITDA` | Proposed - quarterly normalization required |

### Quarterly-Only Momentum Indicators

Quarter-over-quarter indicators provide short-horizon evidence but should appear
beside, not replace, the less seasonal year-over-year quarterly indicators.

| Quarterly indicator | Formula | Status |
| --- | --- | --- |
| `revenue_growth_qoq` | `(revenue_q - revenue_prior_q) / abs(revenue_prior_q)` | Proposed - quarterly normalization required |
| `operating_income_growth_qoq` | `(operating_income_q - operating_income_prior_q) / abs(operating_income_prior_q)` | Proposed - quarterly normalization required |
| `diluted_eps_growth_qoq` | `(diluted_eps_q - diluted_eps_prior_q) / abs(diluted_eps_prior_q)` | Proposed - quarterly normalization required |
| `free_cash_flow_growth_qoq` | `(free_cash_flow_q - free_cash_flow_prior_q) / abs(free_cash_flow_prior_q)` | Proposed - quarterly normalization required |

The prior quarter resolver must cross fiscal-year boundaries correctly. For
example, the prior quarter for fiscal 2026 Q1 is fiscal 2025 Q4, not fiscal 2025
Q1. Skip QoQ growth when the prior discrete quarter or a valid derived Q4 is not
available.

### Period Rules for Proposed Industry Indicators

The industry tables below define business applicability. Apply these additional
period rules:

- Pure duration-to-duration ratios and YoY growth formulas can run for annual
  and discrete-quarter periods when both inputs use the same basis.
- Pure instant ratios can run at fiscal year end and quarter end.
- Turnover formulas that divide a flow by an average balance use their existing
  names annually and must use a distinct `_ttm` name in quarterly output.
- Use `net_interest_margin_annual` for a full-year calculation and
  `net_interest_margin_quarterly_annualized` for annualized discrete-quarter net
  interest income over average earning assets. Store the basis in formula
  metadata.
- Insurance loss and combined ratios can run annually or on consistent
  discrete-quarter earned-premium and expense bases; do not mix gross and net
  measures.
- REIT FFO can run annually or quarterly only when the complete reconciliation
  uses the same period basis. FFO remains supplemental non-GAAP evidence.
- Ratios such as backlog-to-revenue, deferred-revenue-to-revenue,
  PP&E turnover, utility-plant turnover, and real-estate asset turnover use an
  annual flow denominator in the yearly table and require a distinct TTM
  denominator and name in the quarterly table.

## Industry Bundles

The tables below list indicators added to the common core. An implemented
formula being listed here means it is suitable for the bundle; it does not mean
industry-based runtime selection is already implemented.

### Energy

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `gross_margin` | `gross_profit / revenue` | Implemented | Use only when gross profit is reported consistently. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Interpret against capital-intensive Energy peers, not as a cross-industry benchmark. |
| `operating_cash_flow_margin` | `operating_cash_flow / revenue` | Implemented | Same currency and period. |
| `free_cash_flow` | `operating_cash_flow - abs(capital_expenditure)` | Implemented | Treat as derived, not reported. |
| `free_cash_flow_margin` | `free_cash_flow / revenue` | Implemented | Preserve operating-cash-flow and capex lineage. |
| `free_cash_flow_growth_yoy` | YoY growth in derived `free_cash_flow` | Implemented | Requires comparable current and prior FCF. |
| `capex_intensity` | `abs(capital_expenditure) / revenue` | Implemented | Useful for capital-heavy operations. |
| `debt_to_equity` | `total_debt / shareholders_equity` | Implemented | Use only the approved non-overlapping debt component policy. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `interest_coverage` | `operating_income / abs(interest_expense)` | Implemented | Do not substitute capitalized interest. |
| `days_inventory_outstanding` | `(average_inventory / cost_of_revenue) * period_days` | Implemented | Input-qualified for companies with meaningful physical inventory. |
| `ppe_turnover` | `revenue / average_property_plant_and_equipment` | Proposed - catalog inputs exist | Requires current and prior net PP&E. |
| `asset_retirement_obligation_to_ppe` | `asset_retirement_obligation / property_plant_and_equipment` | Proposed - catalog inputs exist | Exposure indicator; not a measure of funded coverage. |
| `capex_to_operating_cash_flow` | `abs(capital_expenditure) / operating_cash_flow` | Proposed - catalog inputs exist | Skip non-positive operating cash flow. |

Oil and gas reserve replacement, production growth, and lifting-cost indicators
are not in the initial bundle because the current target catalog does not define
auditable normalized reserve or production metrics.

### Materials

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `gross_margin` | `gross_profit / revenue` | Implemented | Use only when gross profit is available. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `cost_of_revenue_ratio` | `cost_of_revenue / revenue` | Implemented | Same-period duration metrics only. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Requires current and prior comparable total assets. |
| `free_cash_flow` | `operating_cash_flow - abs(capital_expenditure)` | Implemented | Same currency and period. |
| `free_cash_flow_margin` | `free_cash_flow / revenue` | Implemented | Preserve source lineage. |
| `capex_intensity` | `abs(capital_expenditure) / revenue` | Implemented | Useful for production capacity requirements. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `interest_coverage` | `operating_income / abs(interest_expense)` | Implemented | Requires a usable interest-expense metric. |
| `days_sales_outstanding` | `(average_accounts_receivable / revenue) * period_days` | Implemented | Requires comparable receivables. |
| `days_inventory_outstanding` | `(average_inventory / cost_of_revenue) * period_days` | Implemented | Requires comparable inventory. |
| `days_payable_outstanding` | `(average_accounts_payable / cost_of_revenue) * period_days` | Implemented | Requires comparable payables. |
| `cash_conversion_cycle` | `DSO + DIO - DPO` | Implemented | Calculate only when all three components are supported. |
| `ppe_turnover` | `revenue / average_property_plant_and_equipment` | Proposed - catalog inputs exist | Requires current and prior net PP&E. |
| `environmental_remediation_cost_ratio` | `environmental_remediation_expense / revenue` | Proposed - catalog inputs exist | Expense must represent the same period and currency as revenue. |
| `asset_retirement_obligation_to_ppe` | `asset_retirement_obligation / property_plant_and_equipment` | Proposed - catalog inputs exist | Exposure indicator; do not interpret as reserve adequacy. |

### Industrials

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `gross_margin` | `gross_profit / revenue` | Implemented | Use only when gross profit is reported. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `cost_of_revenue_ratio` | `cost_of_revenue / revenue` | Implemented | Same-period duration metrics only. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Requires current and prior comparable total assets. |
| `free_cash_flow_margin` | `free_cash_flow / revenue` | Implemented | Preserve FCF source lineage. |
| `capex_intensity` | `abs(capital_expenditure) / revenue` | Implemented | Useful for manufacturing-heavy companies. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `interest_coverage` | `operating_income / abs(interest_expense)` | Implemented | Requires usable interest expense. |
| `days_sales_outstanding` | `(average_accounts_receivable / revenue) * period_days` | Implemented | Requires comparable receivables. |
| `days_inventory_outstanding` | `(average_inventory / cost_of_revenue) * period_days` | Implemented | Input-qualified for inventory-bearing operations. |
| `days_payable_outstanding` | `(average_accounts_payable / cost_of_revenue) * period_days` | Implemented | Requires comparable payables. |
| `cash_conversion_cycle` | `DSO + DIO - DPO` | Implemented | Calculate only when all components are supported. |
| `backlog_growth_yoy` | `(backlog_t - backlog_t-1) / abs(backlog_t-1)` | Proposed - catalog inputs exist | Backlog definitions must be comparable across filings. |
| `backlog_to_revenue` | `backlog / revenue` | Proposed - catalog inputs exist | Treat backlog as an instant operating metric, not recognized revenue. |
| `contract_asset_to_revenue` | `contract_assets_current / revenue` | Proposed - catalog inputs exist | Label as a balance-to-flow ratio. |
| `contract_liability_to_revenue` | `contract_liabilities_current / revenue` | Proposed - catalog inputs exist | Do not call all contract liabilities backlog. |
| `ppe_turnover` | `revenue / average_property_plant_and_equipment` | Proposed - catalog inputs exist | Requires current and prior net PP&E. |

### Consumer Discretionary

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `gross_margin` | `gross_profit / revenue` | Implemented | Use only when gross profit is reported. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `sga_intensity` | `selling_general_and_administrative_expense / revenue` | Implemented | Use only when SG&A is reported separately. |
| `cost_of_revenue_ratio` | `cost_of_revenue / revenue` | Implemented | Same-period duration metrics only. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Useful for comparing store, platform, and manufacturing asset use within similar business models. |
| `free_cash_flow_margin` | `free_cash_flow / revenue` | Implemented | Preserve FCF source lineage. |
| `capex_intensity` | `abs(capital_expenditure) / revenue` | Implemented | Useful for stores, logistics, and manufacturing assets. |
| `current_ratio` | `current_assets / current_liabilities` | Implemented | General liquidity context, not a standalone conclusion. |
| `quick_ratio` | `(cash + short_term_investments + receivables) / current_liabilities` | Implemented | Requires every numerator component. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `interest_coverage` | `operating_income / abs(interest_expense)` | Implemented | Requires usable interest expense. |
| `days_sales_outstanding` | `(average_accounts_receivable / revenue) * period_days` | Implemented | Input-qualified for receivables-bearing businesses. |
| `days_inventory_outstanding` | `(average_inventory / cost_of_revenue) * period_days` | Implemented | Input-qualified for inventory-bearing businesses. |
| `days_payable_outstanding` | `(average_accounts_payable / cost_of_revenue) * period_days` | Implemented | Requires comparable payables. |
| `cash_conversion_cycle` | `DSO + DIO - DPO` | Implemented | Calculate only when all components are supported. |
| `advertising_intensity` | `advertising_expense / revenue` | Proposed - catalog inputs exist | Use only when advertising expense is separately reported. |
| `operating_lease_liability_to_revenue` | `(operating_lease_liability_current + operating_lease_liability_noncurrent) / revenue` | Proposed - catalog inputs exist | Balance-to-flow exposure ratio; keep units and period labels explicit. |
| `lease_adjusted_debt_to_equity` | `(total_debt + operating_lease_liabilities) / shareholders_equity` | Proposed - catalog inputs exist | Avoid double-counting lease liabilities already included in approved debt components. |

### Consumer Staples

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `gross_margin` | `gross_profit / revenue` | Implemented | Use only when gross profit is reported. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `sga_intensity` | `selling_general_and_administrative_expense / revenue` | Implemented | Use only when SG&A is separately reported. |
| `cost_of_revenue_ratio` | `cost_of_revenue / revenue` | Implemented | Same-period duration metrics only. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Compare within similar retail and branded-product models. |
| `free_cash_flow_margin` | `free_cash_flow / revenue` | Implemented | Preserve FCF source lineage. |
| `current_ratio` | `current_assets / current_liabilities` | Implemented | General liquidity context only. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `interest_coverage` | `operating_income / abs(interest_expense)` | Implemented | Requires usable interest expense. |
| `days_sales_outstanding` | `(average_accounts_receivable / revenue) * period_days` | Implemented | Requires comparable receivables. |
| `days_inventory_outstanding` | `(average_inventory / cost_of_revenue) * period_days` | Implemented | Core bundle measure for inventory-bearing operations. |
| `days_payable_outstanding` | `(average_accounts_payable / cost_of_revenue) * period_days` | Implemented | Requires comparable payables. |
| `cash_conversion_cycle` | `DSO + DIO - DPO` | Implemented | Calculate only when all components are supported. |
| `advertising_intensity` | `advertising_expense / revenue` | Proposed - catalog inputs exist | Use only when advertising expense is separately reported. |
| `operating_lease_liability_to_revenue` | `(operating_lease_liability_current + operating_lease_liability_noncurrent) / revenue` | Proposed - catalog inputs exist | Useful for store-heavy companies; not universal within the label. |
| `lease_adjusted_debt_to_equity` | `(total_debt + operating_lease_liabilities) / shareholders_equity` | Proposed - catalog inputs exist | Avoid double-counting approved debt components. |

### Health Care

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `gross_margin` | `gross_profit / revenue` | Implemented | Use only when gross profit is reported. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `rd_intensity` | `research_and_development_expense / revenue` | Implemented | Primary for pharmaceutical, biotech, and device companies that report R&D. |
| `sga_intensity` | `selling_general_and_administrative_expense / revenue` | Implemented | Use only when SG&A is separately reported. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Input-qualified and most useful within similar product or provider business models. |
| `free_cash_flow_margin` | `free_cash_flow / revenue` | Implemented | Preserve FCF source lineage. |
| `cash_earnings_conversion` | `operating_cash_flow / net_income` | Implemented | Skip zero net income; interpret negative earnings carefully. |
| `capex_intensity` | `abs(capital_expenditure) / revenue` | Implemented | Useful for manufacturing and care-delivery assets. |
| `current_ratio` | `current_assets / current_liabilities` | Implemented | General liquidity context only. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `days_sales_outstanding` | `(average_accounts_receivable / revenue) * period_days` | Implemented | Useful for providers and product companies with material receivables. |
| `days_inventory_outstanding` | `(average_inventory / cost_of_revenue) * period_days` | Implemented | Input-qualified for product and device companies. |
| `rd_expense_growth_yoy` | YoY growth in `research_and_development_expense` | Proposed - catalog inputs exist | Requires consistent R&D classification. |
| `intangible_assets_to_assets` | `intangible_assets / total_assets` | Proposed - catalog inputs exist | Indicates acquisition and intellectual-property balance-sheet exposure. |
| `goodwill_to_assets` | `goodwill / total_assets` | Proposed - catalog inputs exist | Exposure indicator; do not infer impairment risk without evidence. |
| `ppe_turnover` | `revenue / average_property_plant_and_equipment` | Proposed - catalog inputs exist | Input-qualified for asset-heavy manufacturers and providers. |

Pipeline success, trial-stage progression, and patent-expiry indicators are not
in the initial bundle because they require validated non-XBRL operating data and
product-level semantic evidence.

### Financials

`Financials` contains materially different business models. Banking and
insurance indicators are input-qualified sub-bundles; the presence of the broad
label alone must not cause every formula below to run.

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `net_interest_income_growth_yoy` | YoY growth in `net_interest_income` | Proposed - catalog inputs exist | Banking sub-bundle only. |
| `net_interest_margin_annual` | `annual_net_interest_income / average_earning_assets` | Proposed - additional inputs required | Banking sub-bundle only; requires an approved `earning_assets` metric. |
| `net_interest_margin_quarterly_annualized` | `(discrete_quarter_net_interest_income * annualization_factor) / average_earning_assets` | Proposed - additional inputs required | Banking sub-bundle only; derive the annualization factor from the quarter's actual dates. |
| `loan_to_deposit_ratio` | `loans_receivable / deposits` | Proposed - catalog inputs exist | Banking sub-bundle only; use net loans consistently. |
| `allowance_for_credit_losses_to_loans` | `allowance_for_credit_losses / loans_receivable` | Proposed - catalog inputs exist | Banking sub-bundle only; this is a reserve-coverage ratio, not realized loss performance. |
| `deposit_growth_yoy` | YoY growth in `deposits` | Proposed - catalog inputs exist | Banking sub-bundle only; compare equivalent period-end balances. |
| `insurance_premium_growth_yoy` | YoY growth in `insurance_premiums` | Proposed - catalog inputs exist | Insurance sub-bundle only. |
| `insurance_loss_ratio` | `insurance_claims_expense / insurance_premiums` | Proposed - catalog inputs exist | Insurance sub-bundle only; claims and premiums must use consistent net/gross bases. |
| `insurance_combined_ratio` | `(insurance_claims_expense + underwriting_expense) / insurance_premiums` | Proposed - additional inputs required | Property and casualty insurance only; requires an approved underwriting-expense metric. |
| `investment_income_to_premiums` | `investment_income / insurance_premiums` | Proposed - catalog inputs exist | Insurance context indicator; do not label it investment yield. |

Do not select generic `current_ratio`, `quick_ratio`, `debt_to_equity`,
`net_debt_to_ebitda`, `free_cash_flow`, or `cash_conversion_cycle` by default for
Financials. Deposits, policy liabilities, regulatory capital, and earning assets
have different economic meanings from ordinary operating-company liabilities
and working capital.

### Information Technology

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `free_cash_flow_growth_yoy` | YoY growth in derived `free_cash_flow` | Implemented | Requires comparable current and prior FCF. |
| `gross_margin` | `gross_profit / revenue` | Implemented | Use only when gross profit is reported. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `rd_intensity` | `research_and_development_expense / revenue` | Implemented | Use only when R&D is separately reported. |
| `sga_intensity` | `selling_general_and_administrative_expense / revenue` | Implemented | Use only when SG&A is separately reported. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Compare hardware, semiconductor, and software models separately. |
| `free_cash_flow_margin` | `free_cash_flow / revenue` | Implemented | Preserve FCF source lineage. |
| `cash_earnings_conversion` | `operating_cash_flow / net_income` | Implemented | Skip zero net income. |
| `capex_intensity` | `abs(capital_expenditure) / revenue` | Implemented | Useful for hardware, semiconductor, cloud, and data-center operations. |
| `current_ratio` | `current_assets / current_liabilities` | Implemented | General liquidity context only. |
| `quick_ratio` | `(cash + short_term_investments + receivables) / current_liabilities` | Implemented | Requires every numerator component. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `days_sales_outstanding` | `(average_accounts_receivable / revenue) * period_days` | Implemented | Useful for enterprise, cloud, and hardware receivables. |
| `deferred_revenue_growth_yoy` | YoY growth in total `deferred_revenue` | Proposed - catalog inputs exist | Combine current and noncurrent balances without double-counting equivalent tags. |
| `deferred_revenue_to_revenue` | `(deferred_revenue_current + deferred_revenue_noncurrent) / revenue` | Proposed - catalog inputs exist | Balance-to-flow context indicator; not remaining performance obligations. |
| `selling_and_marketing_intensity` | `selling_and_marketing_expense / revenue` | Proposed - catalog inputs exist | Use only when reported separately from broader SG&A. |
| `intangible_assets_to_assets` | `intangible_assets / total_assets` | Proposed - catalog inputs exist | Acquisition and intellectual-property exposure indicator. |
| `goodwill_to_assets` | `goodwill / total_assets` | Proposed - catalog inputs exist | Exposure indicator; do not infer impairment without evidence. |

SaaS indicators such as annual recurring revenue growth, net revenue retention,
and customer acquisition efficiency remain deferred until standardized,
traceable operating metrics are available. Deferred revenue is not a substitute
for those metrics.

### Communication Services

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `gross_margin` | `gross_profit / revenue` | Implemented | Use only when gross profit is reported. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `sga_intensity` | `selling_general_and_administrative_expense / revenue` | Implemented | Use only when SG&A is separately reported. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Compare platform, media, and network operators separately. |
| `operating_cash_flow_margin` | `operating_cash_flow / revenue` | Implemented | Same currency and period. |
| `free_cash_flow_margin` | `free_cash_flow / revenue` | Implemented | Preserve FCF source lineage. |
| `free_cash_flow_growth_yoy` | YoY growth in derived `free_cash_flow` | Implemented | Requires comparable current and prior FCF. |
| `capex_intensity` | `abs(capital_expenditure) / revenue` | Implemented | Useful for networks, spectrum-supporting assets, and data centers. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `interest_coverage` | `operating_income / abs(interest_expense)` | Implemented | Requires usable interest expense. |
| `days_sales_outstanding` | `(average_accounts_receivable / revenue) * period_days` | Implemented | Input-qualified for advertising and subscription receivables. |
| `deferred_revenue_growth_yoy` | YoY growth in total `deferred_revenue` | Proposed - catalog inputs exist | Input-qualified for subscription and prepaid service models. |
| `selling_and_marketing_intensity` | `selling_and_marketing_expense / revenue` | Proposed - catalog inputs exist | Use only when separately reported. |
| `goodwill_to_assets` | `goodwill / total_assets` | Proposed - catalog inputs exist | Acquisition exposure indicator. |
| `intangible_assets_to_assets` | `intangible_assets / total_assets` | Proposed - catalog inputs exist | Useful when licenses and acquired intangibles are material. |

Subscriber growth, churn, average revenue per user, audience engagement, and
content-efficiency indicators remain deferred because the current XBRL target
catalog does not normalize those company-specific operating metrics.

### Utilities

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `operating_income_growth_yoy` | YoY growth in `operating_income` | Implemented | Requires comparable operating income. |
| `operating_margin` | `operating_income / revenue` | Implemented | Same-period duration metrics only. |
| `asset_turnover` | `revenue / average_total_assets` | Implemented | Use as secondary context; utility-plant turnover is the more specific proposed measure. |
| `operating_cash_flow_margin` | `operating_cash_flow / revenue` | Implemented | Same currency and period. |
| `free_cash_flow` | `operating_cash_flow - abs(capital_expenditure)` | Implemented | Keep visible but interpret in the context of long regulated investment cycles. |
| `capex_intensity` | `abs(capital_expenditure) / revenue` | Implemented | Primary capital-investment context measure. |
| `debt_to_equity` | `total_debt / shareholders_equity` | Implemented | Use approved non-overlapping debt components. |
| `net_debt_to_ebitda` | `net_debt / EBITDA` | Implemented | Skip non-positive EBITDA. |
| `interest_coverage` | `operating_income / abs(interest_expense)` | Implemented | Requires usable interest expense. |
| `utility_plant_turnover` | `revenue / average_utility_plant` | Proposed - catalog inputs exist | Requires current and prior net utility plant. |
| `plant_investment_rate` | `abs(capital_expenditure) / average_utility_plant` | Proposed - catalog inputs exist | Balance-to-flow measure; label period length explicitly. |
| `capex_to_depreciation` | `abs(capital_expenditure) / depreciation_and_amortization` | Proposed - catalog inputs exist | Skip zero depreciation and preserve matched period units. |
| `asset_retirement_obligation_to_plant` | `asset_retirement_obligation / utility_plant` | Proposed - catalog inputs exist | Exposure indicator; not a measure of regulatory recovery. |

Rate-base growth, allowed return on equity, customer count, generation mix, and
reliability indicators remain deferred until regulated-utility disclosures are
normalized from filing text or a separate authoritative dataset.

### Real Estate

`Real Estate` includes equity REITs, mortgage REITs, and other real-estate
companies. The formulas below are input-qualified. Do not assume an equity-REIT
measure applies to a mortgage REIT.

| Indicator | Formula | Status | Applicability guardrail |
| --- | --- | --- | --- |
| `debt_to_equity` | `total_debt / shareholders_equity` | Implemented | Leverage context only; property-value-based leverage may be more informative when supported. |
| `interest_coverage` | `operating_income / abs(interest_expense)` | Implemented | GAAP context only; property or FFO coverage needs additional inputs. |
| `rental_income_growth_yoy` | YoY growth in `rental_income` | Proposed - catalog inputs exist | Equity/property operating sub-bundle only. |
| `operating_lease_income_growth_yoy` | YoY growth in `operating_lease_income` | Proposed - catalog inputs exist | Use only when the reported concept represents lessor income. |
| `real_estate_asset_turnover` | `rental_income / average_real_estate_investment_property` | Proposed - catalog inputs exist | Equity/property operating sub-bundle only. |
| `real_estate_debt_ratio` | `total_debt / real_estate_investment_property` | Proposed - catalog inputs exist | Uses book-value property, not market value or net asset value. |
| `mortgage_loans_to_real_estate_assets` | `mortgage_loans_on_real_estate / real_estate_investment_property` | Proposed - catalog inputs exist | Input-qualified; interpret the numerator and denominator scope carefully. |
| `accumulated_real_estate_depreciation_ratio` | `accumulated_depreciation / (net_real_estate_property + accumulated_depreciation)` | Proposed - catalog inputs exist | Requires compatible property scopes and units. |
| `funds_from_operations` | Nareit FFO reconciliation from GAAP net income | Proposed - additional inputs required | Equity REITs only. Requires real-estate depreciation/amortization, gains or losses on property sales, impairments, and applicable unconsolidated-venture adjustments. Keep it labeled as supplemental non-GAAP. |
| `funds_from_operations_growth_yoy` | YoY growth in reconciled `funds_from_operations` | Proposed - additional inputs required | Calculate only after a complete, traceable FFO reconciliation exists. |

Adjusted funds from operations is not in the initial catalog. Definitions vary,
and the project excludes non-GAAP reconciliation beyond what can be supported
clearly and consistently from filing evidence.

## Industry-Specific Annual and Quarterly Split

The industry bundles and the period catalogs are both required. An industry
indicator not listed as a period difference below is eligible for both annual
FY and discrete-quarter calculation when its formula uses compatible inputs.
The general period-normalization and input-qualification rules still apply.

The quarterly replacement names below are proposed. They are not part of the
current 28-indicator runtime registry.

| Quarterly replacement family | Formula rule |
| --- | --- |
| `ppe_turnover_ttm` | `TTM_revenue / average_property_plant_and_equipment` |
| `backlog_to_revenue_ttm` | `quarter_end_backlog / TTM_revenue` |
| `contract_asset_to_revenue_ttm` | `quarter_end_contract_assets / TTM_revenue` |
| `contract_liability_to_revenue_ttm` | `quarter_end_contract_liabilities / TTM_revenue` |
| `operating_lease_liability_to_revenue_ttm` | `quarter_end_operating_lease_liabilities / TTM_revenue` |
| `deferred_revenue_to_revenue_ttm` | `quarter_end_deferred_revenue / TTM_revenue` |
| `utility_plant_turnover_ttm` | `TTM_revenue / average_utility_plant` |
| `plant_investment_rate_ttm` | `abs(TTM_capital_expenditure) / average_utility_plant` |
| `real_estate_asset_turnover_ttm` | `TTM_rental_income / average_real_estate_investment_property` |

For every average-balance denominator, use compatible quarter-end balances one
year apart unless the formula registry later adopts a more granular documented
average. Skip rather than mix incompatible scopes or dates.

### Energy Period Split

- Annual only: `asset_turnover`, `net_debt_to_ebitda`, `ppe_turnover`.
- Quarterly only: `asset_turnover_ttm`, `net_debt_to_ebitda_ttm`,
  `ppe_turnover_ttm`.
- Both: all other selected Energy indicators, including capex, cash-flow,
  margin, interest-coverage, inventory-days, and asset-retirement-obligation
  ratios, subject to discrete-quarter inputs.

### Materials Period Split

- Annual only: `asset_turnover`, `net_debt_to_ebitda`, `ppe_turnover`.
- Quarterly only: `asset_turnover_ttm`, `net_debt_to_ebitda_ttm`,
  `ppe_turnover_ttm`.
- Both: all other selected Materials indicators, including working-capital,
  remediation-expense, and asset-retirement-obligation ratios.

### Industrials Period Split

- Annual only: `asset_turnover`, `net_debt_to_ebitda`, `ppe_turnover`,
  `backlog_to_revenue`, `contract_asset_to_revenue`, and
  `contract_liability_to_revenue`.
- Quarterly only: `asset_turnover_ttm`, `net_debt_to_ebitda_ttm`,
  `ppe_turnover_ttm`, `backlog_to_revenue_ttm`,
  `contract_asset_to_revenue_ttm`, and `contract_liability_to_revenue_ttm`.
- Both: all other selected Industrials indicators. `backlog_growth_yoy` can run
  at FY end or quarter end because it compares like-for-like instant balances.

### Consumer Discretionary Period Split

- Annual only: `asset_turnover`, `net_debt_to_ebitda`, and
  `operating_lease_liability_to_revenue`.
- Quarterly only: `asset_turnover_ttm`, `net_debt_to_ebitda_ttm`, and
  `operating_lease_liability_to_revenue_ttm`.
- Both: all other selected Consumer Discretionary indicators, including
  advertising intensity, lease-adjusted debt to equity, liquidity, margins,
  and working-capital indicators.

### Consumer Staples Period Split

- Annual only: `asset_turnover`, `net_debt_to_ebitda`, and
  `operating_lease_liability_to_revenue`.
- Quarterly only: `asset_turnover_ttm`, `net_debt_to_ebitda_ttm`, and
  `operating_lease_liability_to_revenue_ttm`.
- Both: all other selected Consumer Staples indicators, including advertising,
  lease-adjusted leverage, inventory-days, and cash-conversion-cycle measures.

### Health Care Period Split

- Annual only: `asset_turnover`, `net_debt_to_ebitda`, and `ppe_turnover`.
- Quarterly only: `asset_turnover_ttm`, `net_debt_to_ebitda_ttm`, and
  `ppe_turnover_ttm`.
- Both: all other selected Health Care indicators, including R&D intensity,
  R&D growth, intangible-assets exposure, goodwill exposure, margins, and
  applicable working-capital measures.

### Financials Period Split

- Annual only: `net_interest_margin_annual` for the banking sub-bundle.
- Quarterly only: `net_interest_margin_quarterly_annualized` for the banking
  sub-bundle.
- Both: `net_interest_income_growth_yoy`, `loan_to_deposit_ratio`,
  `allowance_for_credit_losses_to_loans`, `deposit_growth_yoy`,
  `insurance_premium_growth_yoy`, `insurance_loss_ratio`,
  `insurance_combined_ratio`, and `investment_income_to_premiums` when their
  banking or insurance input qualification is satisfied.
- Quarterly insurance ratios must use consistent discrete-quarter earned
  premiums, claims, and expenses. Do not mix YTD expenses with quarterly
  premiums.

### Information Technology Period Split

- Annual only: `asset_turnover`, `net_debt_to_ebitda`, and
  `deferred_revenue_to_revenue`.
- Quarterly only: `asset_turnover_ttm`, `net_debt_to_ebitda_ttm`, and
  `deferred_revenue_to_revenue_ttm`.
- Both: all other selected Information Technology indicators. In particular,
  `deferred_revenue_growth_yoy` compares like-for-like period-end balances and
  does not require a TTM denominator.

### Communication Services Period Split

- Annual only: `asset_turnover` and `net_debt_to_ebitda`.
- Quarterly only: `asset_turnover_ttm` and `net_debt_to_ebitda_ttm`.
- Both: all other selected Communication Services indicators, including
  deferred-revenue growth, selling-and-marketing intensity, goodwill and
  intangible exposure, margins, cash flow, and interest coverage.

### Utilities Period Split

- Annual only: `asset_turnover`, `net_debt_to_ebitda`,
  `utility_plant_turnover`, and `plant_investment_rate`.
- Quarterly only: `asset_turnover_ttm`, `net_debt_to_ebitda_ttm`,
  `utility_plant_turnover_ttm`, and `plant_investment_rate_ttm`.
- Both: all other selected Utilities indicators, including capex intensity,
  capex to depreciation, debt to equity, interest coverage, and
  asset-retirement-obligation exposure.

### Real Estate Period Split

- Annual only: `real_estate_asset_turnover`.
- Quarterly only: `real_estate_asset_turnover_ttm`.
- Both: `debt_to_equity`, `interest_coverage`, `rental_income_growth_yoy`,
  `operating_lease_income_growth_yoy`, `real_estate_debt_ratio`,
  `mortgage_loans_to_real_estate_assets`, and
  `accumulated_real_estate_depreciation_ratio` when input qualification is met.
- `funds_from_operations` and `funds_from_operations_growth_yoy` can run on an
  annual or discrete-quarter basis only when each period has a complete,
  consistent Nareit reconciliation. Quarterly FFO must never reuse an annual or
  YTD reconciliation unchanged.

## Current Implementation Gap

This document describes the desired catalog boundary, not current runtime
selection. Before industry-aware calculation is implemented, the project still
needs to decide and test:

1. How indicator definitions declare `common` versus one or more hard industry
   labels without changing the meaning of existing formulas.
2. How input-qualified sub-bundles are selected deterministically.
3. How reports distinguish `not_applicable` from existing calculation skip
   reasons such as `missing_required_metric`.
4. Whether catalog-selection provenance belongs only in report output or also
   requires a storage change. Any database schema change requires explicit user
   confirmation.
5. Which proposed metric mappings are sufficiently complete and non-ambiguous
   to activate each new formula.
6. Focused tests for multi-label union, de-duplication, industry exclusions,
   missing inputs, period comparability, unit mismatches, and source lineage.
7. A duration-basis model that distinguishes annual, discrete quarter,
   year-to-date, derived Q4, and TTM values before indicator calculation.
8. Separate annual and quarterly indicator selection, including `_ttm` and
   `_qoq` definitions and a deterministic `not_applicable_for_period` outcome.
9. Per-industry period eligibility so an industry-specific annual formula is
   replaced by its quarterly TTM definition instead of being reused unchanged.

Until that work is implemented, reports should describe the 28 existing
formulas as the **current implemented registry**, not as the correct universal
indicator set for every industry or every reporting period. The current engine
still applies all 28 definitions to every active FY and Q period, and its metric
lookup does not yet distinguish a discrete quarter from a year-to-date duration.

## Project References

- `src/indicators/formulas.py`: current deterministic 28-indicator registry.
- `src/indicators/engine.py`: current calculation and skip behavior.
- `src/processing/company_industry_labels.py`: fixed 11-label taxonomy and
  source-controlled company assignments.
- `src/processing/mapping_catalog.py`: common and industry-specific source
  metric targets used to judge whether proposed formulas have catalog inputs.
- `docs/mapping_policy.md`: industry-label and mapping governance.
- `proposal.md`: project scope, including the requirement to keep specialized
  indicator catalogs explicit rather than forcing one universal catalog.

## External Definition References

- [FDIC examination manual, Earnings](https://www.fdic.gov/resources/supervision-and-examinations/examination-policies-manual/section5-1.pdf): net interest margin uses annualized net interest income over average earning assets.
- [FDIC loan-to-deposit guidance](https://www.fdic.gov/federal-register-publications/fdic-federal-register-citations-7504): loan-to-deposit uses net loans and leases divided by total deposits.
- [FDIC allowance for loan and lease losses](https://www.fdic.gov/accounting/allowance-loan-and-lease-losses-alll): the allowance is a valuation allowance against the loan and lease portfolio.
- [NAIC glossary](https://content.naic.org/glossary-insurance-terms): combined ratio is the sum of loss and expense ratios.
- [Nareit 2018 FFO white paper](https://www.reit.com/sites/default/files/2018-FFO-white-paper-%2811-27-18%29.pdf): industry definition and reconciliation considerations for FFO.
- [SEC non-GAAP financial measure guidance](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/non-gaap-financial-measures): SEC staff guidance on Nareit-defined FFO and non-GAAP presentation.
- [SEC Form 10-Q](https://www.sec.gov/files/form10-q.pdf): quarterly-report form and its Rule 10-01 interim-financial-statement requirement.
- [SEC Form 10-K](https://www.sec.gov/files/form10-k.pdf): annual-report form and filing requirements.
