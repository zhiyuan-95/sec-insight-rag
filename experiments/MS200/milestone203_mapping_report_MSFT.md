# Milestone 203 Arelle Mapping Inspection

This report presents the existing workflow. It does not change schemas, write data,
activate inferred mappings, generate formulas, or call an LLM.

## 0. Workflow Walkthrough

| Stage | Input | Action | Output | Stop boundary | Count / time | Inspect |
|---|---|---|---|---|---|---|
| SEC acquisition | `MSFT` + requested forms | Fetch identity, submissions, filings, Company Facts | 2 form records | Network acquisition only | 1.501s | [Summary](#a-summary) |
| Arelle processing | Verified accession packages | Offline load, validation, extraction | 3,451 facts / 887 QNames | Detached project records | 71.874s proof session | [Per-accession evidence](#a1-per-accession-evidence) |
| Fact selection | Arelle facts | Duplicate, nil, degraded, and precedence handling | 3,023 selected / 196 quarantined semantic observations | In memory only | 3,451 raw occurrences | [Selection accounting](#a2-selection-accounting) |
| Target selection | Source-controlled company labels | Common bundle + applicable industry bundle | 38 target metrics | No new target identity | `assigned` | [Mapping status](#b-target-metrics-mapping-status) |
| Hard mapping | Selected facts + catalog + approved SQLite rows | Existing deterministic mapper | 18 mapped / 20 missing targets | No metric persistence | 95 mapped fact observations | [Mapped targets](#b1-mapped-targets) |
| Evidence inference | Missing targets + Arelle taxonomy evidence | Deterministic shadow ranking | 0 unique / 0 review / 20 none | Never activated | 0 LLM calls | [Inference](#c-arelle-evidence-inference) |
| Report publication | Structured session evidence | Render and atomic replace | This Markdown artifact | Presentation only | 1.928s before publication | [Boundary](#d-interpretation-boundary) |

## A. Summary

- Ticker / CIK: `MSFT` / `0000789019`
- Requested forms: `10-K, 10-Q`
- Completion index: `100.0` (complete requested forms / requested forms x 100; higher means more complete)
- Arelle result complete for every requested form: `Y`
- Raw facts processed: 3,451
- Raw QName concepts involved: 887
- Selected eligible semantic observations: 3,023
- Quarantined semantic observations: 196
- Duplicate groups / raw occurrences: 192 / 424
- Fact eligible for mapping: `Y`
- Count integrity: `Y` (3,451 raw = 3,023 selected occurrences + 428 quarantined occurrences)
- Industry bundle: `Information Technology, Communication Services`
- Industry-label status: `assigned`
- Read-only mapping database: `C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\stock_data.db`
- Approved mapping store status: `table_missing_read_only; source-controlled mappings only`
- Approved-mapping selector conflicts excluded: 0
- Proof workflow elapsed: 71.874s
- Report projection elapsed before atomic publication: 1.928s
- Shadow inference policy: `arelle-evidence-inference-v1`; threshold `uncalibrated_shadow`; evidence independence `not_assumed`.
- External model/provider calls during mapping and inference: `0`.

### A1. Per-accession evidence

| Form | Accession | Arelle complete? | Reason when no | Raw facts | QName concepts | Selected | Quarantined | Duplicate groups | Fact eligible? | Arelle seconds |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 10-K | `0000950170-25-100235` | Y |  | 1,829 | 515 | 1,603 | 105 | 103 | Y | 23.098 |
| 10-Q | `0001193125-26-191507` | Y |  | 1,622 | 372 | 1,420 | 91 | 89 | Y | 27.793 |

### A2. Selection accounting

Quarantine reasons may overlap; a duplicate in a degraded accession is counted under both reason labels.
Raw-occurrence integrity uses each semantic observation's occurrence count, not the number of grouped rows.

- `duplicate_fact`: 192 semantic observations
- `nil_fact`: 4 semantic observations

## B. Target Metrics Mapping Status

All 38 applicable canonical targets are shown exactly once below.
The target objects come from the existing catalog; statement type is metadata, not a new metric identity.

### B1. Mapped targets

| Metric | Statement | Source concept and mapping authority | Mapped observations |
|---|---|---|---:|
| `accounts_payable` | `balance_sheet` | us-gaap:AccountsPayableCurrent via source-controlled hard mapping | 4 |
| `accounts_receivable` | `balance_sheet` | us-gaap:AccountsReceivableNetCurrent via source-controlled hard mapping | 4 |
| `amortization_of_intangible_assets` | `cash_flow_statement` | us-gaap:AmortizationOfIntangibleAssets via source-controlled hard mapping | 7 |
| `capital_expenditure` | `cash_flow_statement` | us-gaap:PaymentsToAcquirePropertyPlantAndEquipment via source-controlled hard mapping | 7 |
| `current_assets` | `balance_sheet` | us-gaap:AssetsCurrent via source-controlled hard mapping | 4 |
| `current_liabilities` | `balance_sheet` | us-gaap:LiabilitiesCurrent via source-controlled hard mapping | 4 |
| `deferred_revenue_current` | `balance_sheet` | us-gaap:ContractWithCustomerLiabilityCurrent via source-controlled hard mapping | 4 |
| `deferred_revenue_noncurrent` | `balance_sheet` | us-gaap:ContractWithCustomerLiabilityNoncurrent via source-controlled hard mapping | 4 |
| `depreciation` | `cash_flow_statement` | us-gaap:Depreciation via source-controlled hard mapping | 7 |
| `goodwill` | `balance_sheet` | us-gaap:Goodwill via source-controlled hard mapping | 1 |
| `gross_profit` | `income_statement` | us-gaap:GrossProfit via source-controlled hard mapping | 7 |
| `interest_expense` | `income_statement` | us-gaap:InterestExpenseNonoperating via source-controlled hard mapping | 7 |
| `operating_cash_flow` | `cash_flow_statement` | us-gaap:NetCashProvidedByUsedInOperatingActivities via source-controlled hard mapping | 7 |
| `research_and_development_expense` | `income_statement` | us-gaap:ResearchAndDevelopmentExpense via source-controlled hard mapping | 7 |
| `selling_and_marketing_expense` | `income_statement` | us-gaap:SellingAndMarketingExpense via source-controlled hard mapping | 7 |
| `shareholders_equity` | `balance_sheet` | us-gaap:StockholdersEquity via source-controlled hard mapping | 2 |
| `total_assets` | `balance_sheet` | us-gaap:Assets via source-controlled hard mapping | 4 |
| `total_liabilities` | `balance_sheet` | us-gaap:Liabilities via source-controlled hard mapping | 4 |

### B2. Missing targets

| Metric | Statement | Governed raw-concept aliases | Status |
|---|---|---|---|
| `cash_and_equivalents` | `balance_sheet` | CashAndCashEquivalentsAtCarryingValue | `explicitly_missing` |
| `cost_of_revenue` | `income_statement` | CostOfGoodsAndServicesSold, CostOfRevenue | `explicitly_missing` |
| `debt_current` | `balance_sheet` | DebtCurrent | `explicitly_missing` |
| `debt_noncurrent` | `balance_sheet` | DebtNoncurrent | `explicitly_missing` |
| `depreciation_and_amortization` | `cash_flow_statement` | DepreciationAmortizationAndAccretionNet, DepreciationAndAmortization, DepreciationDepletionAndAmortization, DepreciationDepletionAndAmortizationExpense | `explicitly_missing` |
| `diluted_eps` | `income_statement` | EarningsPerShareBasicAndDiluted, EarningsPerShareDiluted | `explicitly_missing` |
| `finance_lease_liability_current` | `balance_sheet` | FinanceLeaseLiabilityCurrent | `explicitly_missing` |
| `finance_lease_liability_noncurrent` | `balance_sheet` | FinanceLeaseLiabilityNoncurrent | `explicitly_missing` |
| `intangible_assets` | `balance_sheet` | IntangibleAssetsNetExcludingGoodwill | `explicitly_missing` |
| `long_term_debt_and_finance_lease_obligations_current` | `balance_sheet` | LongTermDebtAndFinanceLeaseObligationsCurrent | `explicitly_missing` |
| `long_term_debt_and_finance_lease_obligations_noncurrent` | `balance_sheet` | LongTermDebtAndFinanceLeaseObligationsNoncurrent | `explicitly_missing` |
| `long_term_debt_current` | `balance_sheet` | LongTermDebtCurrent | `explicitly_missing` |
| `long_term_debt_noncurrent` | `balance_sheet` | LongTermDebtNoncurrent | `explicitly_missing` |
| `net_income` | `income_statement` | NetIncomeLoss, ProfitLoss | `explicitly_missing` |
| `operating_income` | `income_statement` | OperatingIncomeLoss | `explicitly_missing` |
| `revenue` | `income_statement` | RevenueFromContractWithCustomerExcludingAssessedTax, RevenueFromContractWithCustomerIncludingAssessedTax, Revenues, SalesRevenueNet | `explicitly_missing` |
| `selling_general_and_administrative_expense` | `income_statement` | SellingGeneralAndAdministrativeExpense | `explicitly_missing` |
| `short_term_borrowings` | `balance_sheet` | ShortTermBorrowings | `explicitly_missing` |
| `short_term_investments` | `balance_sheet` | AvailableForSaleSecuritiesCurrent, HeldToMaturitySecuritiesCurrent, InvestmentsCurrent, MarketableSecuritiesCurrent, OtherShortTermInvestments, ShortTermInvestments, TradingSecuritiesCurrent | `explicitly_missing` |
| `weighted_average_diluted_shares` | `shares` | WeightedAverageNumberOfDilutedSharesOutstanding, WeightedAverageNumberOfSharesOutstandingBasicAndDiluted | `explicitly_missing` |

## C. Arelle-evidence inference

Inference is evaluated only for B2 targets. Scores rank candidates within this run;
they are not confidence values and cannot supply a system metric without the separate approval workflow.
Observation-gate rejection totals count observations; `insufficient_compatibility_evidence` counts candidate concept groups.

| Missing metric | Statement | Outcome | Top candidate | Score / 10 | Target margin | Cross-target margin | Accepted / rejected observations; accessions |
|---|---|---|---|---:|---:|---:|---:|
| `cash_and_equivalents` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `debt_current` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `debt_noncurrent` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `finance_lease_liability_current` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `finance_lease_liability_noncurrent` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `intangible_assets` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `long_term_debt_and_finance_lease_obligations_current` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `long_term_debt_and_finance_lease_obligations_noncurrent` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `long_term_debt_current` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `long_term_debt_noncurrent` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `short_term_borrowings` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `short_term_investments` | `balance_sheet` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `depreciation_and_amortization` | `cash_flow_statement` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `cost_of_revenue` | `income_statement` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `diluted_eps` | `income_statement` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `net_income` | `income_statement` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `operating_income` | `income_statement` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `revenue` | `income_statement` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `selling_general_and_administrative_expense` | `income_statement` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |
| `weighted_average_diluted_shares` | `shares` | `no_candidate` | `none` | 0 | 0 | 0 | 0 / 3023 obs.; 0 / 2 accessions |

### C trace: `cash_and_equivalents` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `debt_current` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `debt_noncurrent` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `finance_lease_liability_current` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `finance_lease_liability_noncurrent` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `intangible_assets` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `long_term_debt_and_finance_lease_obligations_current` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `long_term_debt_and_finance_lease_obligations_noncurrent` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `long_term_debt_current` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `long_term_debt_noncurrent` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `short_term_borrowings` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `short_term_investments` (balance_sheet)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=144; numeric_kind_incompatible=24; period_type_incompatible=833.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0001193125-26-191507 msft:DerivativeAssetStatementOfFinancialPositionExtensibleEnumerationNotDisclosedFlag; 0000950170-25-100235 us-gaap:DerivativeLiabilityCurrentStatementOfFinancialPositionExtensibleEnumeration
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; 0001193125-26-191507 msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets

### C trace: `depreciation_and_amortization` (cash_flow_statement)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=114; numeric_kind_incompatible=220; period_type_incompatible=422.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; us-gaap:AdvertisingExpense; us-gaap:AllocatedShareBasedCompensationExpense
- `numeric_kind_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 dei:AmendmentFlag; 0001193125-26-191507 dei:AmendmentFlag
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AccountsPayableCurrent; 0001193125-26-191507 us-gaap:AccountsPayableCurrent; 0000950170-25-100235 us-gaap:AccountsReceivableNetCurrent

### C trace: `cost_of_revenue` (income_statement)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=114; numeric_kind_incompatible=220; period_type_incompatible=422.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; us-gaap:AdvertisingExpense; us-gaap:AllocatedShareBasedCompensationExpense
- `numeric_kind_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 dei:AmendmentFlag; 0001193125-26-191507 dei:AmendmentFlag
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AccountsPayableCurrent; 0001193125-26-191507 us-gaap:AccountsPayableCurrent; 0000950170-25-100235 us-gaap:AccountsReceivableNetCurrent

### C trace: `diluted_eps` (income_statement)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=114; numeric_kind_incompatible=220; period_type_incompatible=422.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; us-gaap:AdvertisingExpense; us-gaap:AllocatedShareBasedCompensationExpense
- `numeric_kind_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 dei:AmendmentFlag; 0001193125-26-191507 dei:AmendmentFlag
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AccountsPayableCurrent; 0001193125-26-191507 us-gaap:AccountsPayableCurrent; 0000950170-25-100235 us-gaap:AccountsReceivableNetCurrent

### C trace: `net_income` (income_statement)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=114; numeric_kind_incompatible=220; period_type_incompatible=422.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; us-gaap:AdvertisingExpense; us-gaap:AllocatedShareBasedCompensationExpense
- `numeric_kind_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 dei:AmendmentFlag; 0001193125-26-191507 dei:AmendmentFlag
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AccountsPayableCurrent; 0001193125-26-191507 us-gaap:AccountsPayableCurrent; 0000950170-25-100235 us-gaap:AccountsReceivableNetCurrent

### C trace: `operating_income` (income_statement)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=114; numeric_kind_incompatible=220; period_type_incompatible=422.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; us-gaap:AdvertisingExpense; us-gaap:AllocatedShareBasedCompensationExpense
- `numeric_kind_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 dei:AmendmentFlag; 0001193125-26-191507 dei:AmendmentFlag
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AccountsPayableCurrent; 0001193125-26-191507 us-gaap:AccountsPayableCurrent; 0000950170-25-100235 us-gaap:AccountsReceivableNetCurrent

### C trace: `revenue` (income_statement)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=114; numeric_kind_incompatible=220; period_type_incompatible=422.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; us-gaap:AdvertisingExpense; us-gaap:AllocatedShareBasedCompensationExpense
- `numeric_kind_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 dei:AmendmentFlag; 0001193125-26-191507 dei:AmendmentFlag
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AccountsPayableCurrent; 0001193125-26-191507 us-gaap:AccountsPayableCurrent; 0000950170-25-100235 us-gaap:AccountsReceivableNetCurrent

### C trace: `selling_general_and_administrative_expense` (income_statement)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=114; numeric_kind_incompatible=220; period_type_incompatible=422.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets; us-gaap:AdvertisingExpense; us-gaap:AllocatedShareBasedCompensationExpense
- `numeric_kind_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 dei:AmendmentFlag; 0001193125-26-191507 dei:AmendmentFlag
- `period_type_incompatible` examples: 0000950170-25-100235 us-gaap:AccountsPayableCurrent; 0001193125-26-191507 us-gaap:AccountsPayableCurrent; 0000950170-25-100235 us-gaap:AccountsReceivableNetCurrent

### C trace: `weighted_average_diluted_shares` (shares)

- Outcome: `no_candidate` -- No candidate survived the deterministic compatibility gates.
- Top candidate: `none`
- Score categories: statement role 0/2; presentation neighborhood 0/2; calculation/definition network 0/2; cross-form recurrence 0/2; governed lexical evidence 0/2.
- Target-to-concept margin: 0; concept-to-target margin: 0.
- Runner-up: `none` (n/a).
- Strongest competing target: `none` (n/a).
- Accessions: `none`.
- Hard gates: candidate_available=fail.
- Rejections: dimensional_observation=1768; insufficient_compatibility_evidence=258; numeric_kind_incompatible=244.
- `dimensional_observation` examples: 0001193125-26-191507 us-gaap:AccruedIncomeTaxesNoncurrent; 0000950170-25-100235 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment; 0001193125-26-191507 us-gaap:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment
- `insufficient_compatibility_evidence` examples: us-gaap:AccountsPayableCurrent; us-gaap:AccountsReceivableNetCurrent; us-gaap:AccountsReceivableNetNoncurrent
- `numeric_kind_incompatible` examples: 0000950170-25-100235 us-gaap:AcquiredFiniteLivedIntangibleAssetsWeightedAverageUsefulLife; 0000950170-25-100235 dei:AmendmentFlag; 0001193125-26-191507 dei:AmendmentFlag

## C1. Worked workflow traces

- Mapped example `accounts_payable`: selected Arelle observation -> normalized fact -> existing hard mapping (us-gaap:AccountsPayableCurrent via source-controlled hard mapping) -> B1.
- Missing example `cash_and_equivalents`: no usable hard-mapped fact -> B2 -> shadow inference `no_candidate` with candidate `none` -> no activation or write.

## D. Interpretation Boundary

- Arelle supplies parsed facts, QName identity, concept metadata, relationships, and validation evidence. It does not produce universal system-metric labels.
- B1 is the result of the existing deterministic hard mapper, including applicable approved repository mappings.
- B2 remains explicitly missing. Section C is report-only shadow evidence and does not add candidates to the approved dictionary.
- Formula suggestions and all LLM calls are intentionally not run by this experiment.
- Namespace is retained for lineage and collision detection, not used as the normal target-mapping selector.
- No database row, financial metric, inferred mapping, formula, or schema was created or changed.
