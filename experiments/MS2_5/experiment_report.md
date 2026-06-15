# Milestone 2.5 Live SEC Experiment Report

## Human Question

For a company I choose, what does Plan 2.5 ingestion do during setup
and during the next already-ingested session: local existence, refresh
due status, SEC update check, newly ingested filings, next check dates,
and stored evidence?

## Run Context

- ticker: AAPL
- run timestamp: 2026-06-15T21:26:55.847887+00:00
- database: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\experiment.db
- report output: file
- report: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\experiment_report.md
- filings directory: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings
- csv export directory: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\data\exports\ms2_5
- SEC_USER_AGENT configured: yes

## Source Quality Warnings

- Normalized facts include quality flag: ambiguous_unit
- Normalized facts include quality flag: unsupported_form

## Setup Ingestion

- company existed before setup: no
- setup status: initialized
- SEC checked during setup: yes

### Company State

| company_id | cik | name | ticker | exchange | sic | sic_description | latest_10k_filing_date | latest_10q_filing_date | next_check_date_10k | next_check_date_10q | created_at | updated_at |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0000320193 | Apple Inc. | AAPL | Nasdaq | 3571 | Electronic Computers | 2025-10-31 | 2026-05-01 | 2026-10-30 | 2026-07-31 | 2026-06-15T21:27:03.286059+00:00 | 2026-06-15T21:27:03.286059+00:00 |

### Filing Inventory

| form_type | accession_number | filing_date | report_date | fiscal_year | fiscal_period | is_active_window | local_path |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 10-K | 0000320193-25-000079 | 2025-10-31 | 2025-10-17 | 2025 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-25-000079\aap... |
| 10-K | 0000320193-24-000123 | 2024-11-01 | 2024-10-18 | 2024 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-24-000123\aap... |
| 10-K | 0000320193-23-000106 | 2023-11-03 | 2023-10-20 | 2023 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-23-000106\aap... |
| 10-K | 0000320193-22-000108 | 2022-10-28 | 2022-10-14 | 2022 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-22-000108\aap... |
| 10-K | 0000320193-21-000105 | 2021-10-29 | 2021-10-15 | 2021 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-21-000105\aap... |
| 10-Q | 0000320193-26-000013 | 2026-05-01 | 2026-04-17 | 2026 | Q2 | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-26-000013\aap... |
| 10-Q | 0000320193-26-000006 | 2026-01-30 | 2026-01-16 | 2026 | Q1 | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-26-000006\aap... |
| 10-Q | 0000320193-25-000073 | 2025-08-01 | 2025-07-18 | 2025 | Q3 | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-25-000073\aap... |

### Raw Fact And Metric Counts

| table | rows |
| --- | --- |
| companies | 1 |
| filings | 17 |
| raw_xbrl_facts | 24852 |
| financial_metrics | 2198 |

### Active Window

| form | active filings | local accessions |
| --- | --- | --- |
| 10-K | 5 | 0000320193-25-000079, 0000320193-24-000123, 0000320193-23-000106, 0000320193-22-000108, 0000320193-21-000105 |
| 10-Q | 12 | 0000320193-26-000013, 0000320193-26-000006, 0000320193-25-000073, 0000320193-25-000057, 0000320193-25-000008, 0000320... |

Metric counts by statement:

| statement_type | total_metrics | active_metrics |
| --- | --- | --- |
| balance_sheet | 1006 | 254 |
| cash_flow_statement | 229 | 78 |
| income_statement | 963 | 220 |

### Compact financial_metrics Sample

| metric_id | statement_type | metric_name | fiscal_year | fiscal_period | value_numeric | unit | accession_number | raw_fact_id | is_active_window |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 486 | balance_sheet | cash_and_equivalents | 2026 | Q2 | 35934000000 | USD | 0000320193-26-000013 | 2485 | 1 |
| 488 | balance_sheet | cash_and_equivalents | 2026 | Q2 | 45572000000 | USD | 0000320193-26-000013 | 2487 | 1 |
| 485 | balance_sheet | cash_and_equivalents | 2026 | Q1 | 35934000000 | USD | 0000320193-26-000006 | 2484 | 1 |
| 487 | balance_sheet | cash_and_equivalents | 2026 | Q1 | 45317000000 | USD | 0000320193-26-000006 | 2486 | 1 |
| 479 | balance_sheet | cash_and_equivalents | 2025 | Q3 | 29943000000 | USD | 0000320193-25-000073 | 2478 | 1 |
| 483 | balance_sheet | cash_and_equivalents | 2025 | Q3 | 36269000000 | USD | 0000320193-25-000073 | 2482 | 1 |
| 478 | balance_sheet | cash_and_equivalents | 2025 | Q2 | 29943000000 | USD | 0000320193-25-000057 | 2477 | 1 |
| 482 | balance_sheet | cash_and_equivalents | 2025 | Q2 | 28162000000 | USD | 0000320193-25-000057 | 2481 | 1 |

### Compact Traceability Sample

| metric_id | statement_type | metric_name | fiscal_year | fiscal_period | accession_number | raw_fact_id | raw_concept | raw_unit | raw_quality_flags | form_type | filing_date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 486 | balance_sheet | cash_and_equivalents | 2026 | Q2 | 0000320193-26-000013 | 2485 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2026-05-01 |
| 488 | balance_sheet | cash_and_equivalents | 2026 | Q2 | 0000320193-26-000013 | 2487 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2026-05-01 |
| 485 | balance_sheet | cash_and_equivalents | 2026 | Q1 | 0000320193-26-000006 | 2484 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2026-01-30 |
| 487 | balance_sheet | cash_and_equivalents | 2026 | Q1 | 0000320193-26-000006 | 2486 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2026-01-30 |
| 479 | balance_sheet | cash_and_equivalents | 2025 | Q3 | 0000320193-25-000073 | 2478 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2025-08-01 |
| 483 | balance_sheet | cash_and_equivalents | 2025 | Q3 | 0000320193-25-000073 | 2482 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2025-08-01 |
| 478 | balance_sheet | cash_and_equivalents | 2025 | Q2 | 0000320193-25-000057 | 2477 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2025-05-02 |
| 482 | balance_sheet | cash_and_equivalents | 2025 | Q2 | 0000320193-25-000057 | 2481 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2025-05-02 |

### Raw Fact Quality Flags

- ambiguous_unit
- unsupported_form

## Already-Ingested Session Check

| field | value |
| --- | --- |
| company in system | yes |
| update check needed this session | no |
| 10-K check due | no; before=2026-10-30 |
| 10-Q check due | no; before=2026-07-31 |
| SEC update check performed | no |
| SEC result | local data reused; no SEC request made |

### New Filings Ingested During Session

No rows to display.

### Stored Row Deltas During Session

| table | before | after | delta |
| --- | --- | --- | --- |
| companies | 1 | 1 | 0 |
| filings | 17 | 17 | 0 |
| raw_xbrl_facts | 24852 | 24852 | 0 |
| financial_metrics | 2198 | 2198 | 0 |

### Stored Evidence After Session


### Company State

| company_id | cik | name | ticker | exchange | sic | sic_description | latest_10k_filing_date | latest_10q_filing_date | next_check_date_10k | next_check_date_10q | created_at | updated_at |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0000320193 | Apple Inc. | AAPL | Nasdaq | 3571 | Electronic Computers | 2025-10-31 | 2026-05-01 | 2026-10-30 | 2026-07-31 | 2026-06-15T21:27:03.286059+00:00 | 2026-06-15T21:27:03.286059+00:00 |

### Filing Inventory

| form_type | accession_number | filing_date | report_date | fiscal_year | fiscal_period | is_active_window | local_path |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 10-K | 0000320193-25-000079 | 2025-10-31 | 2025-10-17 | 2025 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-25-000079\aap... |
| 10-K | 0000320193-24-000123 | 2024-11-01 | 2024-10-18 | 2024 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-24-000123\aap... |
| 10-K | 0000320193-23-000106 | 2023-11-03 | 2023-10-20 | 2023 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-23-000106\aap... |
| 10-K | 0000320193-22-000108 | 2022-10-28 | 2022-10-14 | 2022 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-22-000108\aap... |
| 10-K | 0000320193-21-000105 | 2021-10-29 | 2021-10-15 | 2021 | FY | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-21-000105\aap... |
| 10-Q | 0000320193-26-000013 | 2026-05-01 | 2026-04-17 | 2026 | Q2 | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-26-000013\aap... |
| 10-Q | 0000320193-26-000006 | 2026-01-30 | 2026-01-16 | 2026 | Q1 | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-26-000006\aap... |
| 10-Q | 0000320193-25-000073 | 2025-08-01 | 2025-07-18 | 2025 | Q3 | 1 | C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\filings\0000320193\0000320193-25-000073\aap... |

### Raw Fact And Metric Counts

| table | rows |
| --- | --- |
| companies | 1 |
| filings | 17 |
| raw_xbrl_facts | 24852 |
| financial_metrics | 2198 |

### Active Window

| form | active filings | local accessions |
| --- | --- | --- |
| 10-K | 5 | 0000320193-25-000079, 0000320193-24-000123, 0000320193-23-000106, 0000320193-22-000108, 0000320193-21-000105 |
| 10-Q | 12 | 0000320193-26-000013, 0000320193-26-000006, 0000320193-25-000073, 0000320193-25-000057, 0000320193-25-000008, 0000320... |

Metric counts by statement:

| statement_type | total_metrics | active_metrics |
| --- | --- | --- |
| balance_sheet | 1006 | 254 |
| cash_flow_statement | 229 | 78 |
| income_statement | 963 | 220 |

### Compact financial_metrics Sample

| metric_id | statement_type | metric_name | fiscal_year | fiscal_period | value_numeric | unit | accession_number | raw_fact_id | is_active_window |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 486 | balance_sheet | cash_and_equivalents | 2026 | Q2 | 35934000000 | USD | 0000320193-26-000013 | 2485 | 1 |
| 488 | balance_sheet | cash_and_equivalents | 2026 | Q2 | 45572000000 | USD | 0000320193-26-000013 | 2487 | 1 |
| 485 | balance_sheet | cash_and_equivalents | 2026 | Q1 | 35934000000 | USD | 0000320193-26-000006 | 2484 | 1 |
| 487 | balance_sheet | cash_and_equivalents | 2026 | Q1 | 45317000000 | USD | 0000320193-26-000006 | 2486 | 1 |
| 479 | balance_sheet | cash_and_equivalents | 2025 | Q3 | 29943000000 | USD | 0000320193-25-000073 | 2478 | 1 |
| 483 | balance_sheet | cash_and_equivalents | 2025 | Q3 | 36269000000 | USD | 0000320193-25-000073 | 2482 | 1 |
| 478 | balance_sheet | cash_and_equivalents | 2025 | Q2 | 29943000000 | USD | 0000320193-25-000057 | 2477 | 1 |
| 482 | balance_sheet | cash_and_equivalents | 2025 | Q2 | 28162000000 | USD | 0000320193-25-000057 | 2481 | 1 |

### Compact Traceability Sample

| metric_id | statement_type | metric_name | fiscal_year | fiscal_period | accession_number | raw_fact_id | raw_concept | raw_unit | raw_quality_flags | form_type | filing_date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 486 | balance_sheet | cash_and_equivalents | 2026 | Q2 | 0000320193-26-000013 | 2485 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2026-05-01 |
| 488 | balance_sheet | cash_and_equivalents | 2026 | Q2 | 0000320193-26-000013 | 2487 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2026-05-01 |
| 485 | balance_sheet | cash_and_equivalents | 2026 | Q1 | 0000320193-26-000006 | 2484 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2026-01-30 |
| 487 | balance_sheet | cash_and_equivalents | 2026 | Q1 | 0000320193-26-000006 | 2486 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2026-01-30 |
| 479 | balance_sheet | cash_and_equivalents | 2025 | Q3 | 0000320193-25-000073 | 2478 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2025-08-01 |
| 483 | balance_sheet | cash_and_equivalents | 2025 | Q3 | 0000320193-25-000073 | 2482 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2025-08-01 |
| 478 | balance_sheet | cash_and_equivalents | 2025 | Q2 | 0000320193-25-000057 | 2477 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2025-05-02 |
| 482 | balance_sheet | cash_and_equivalents | 2025 | Q2 | 0000320193-25-000057 | 2481 | CashAndCashEquivalentsAtCarryingValue | USD | [] | 10-Q | 2025-05-02 |

### Raw Fact Quality Flags

- ambiguous_unit
- unsupported_form

## Full Evidence Artifacts

- SQLite database: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\experiments\MS2_5\experiment.db
- companies CSV: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\data\exports\ms2_5\companies.csv
- filings CSV: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\data\exports\ms2_5\filings.csv
- raw facts CSV: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\data\exports\ms2_5\raw_xbrl_facts.csv
- financial metrics CSV: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\data\exports\ms2_5\financial_metrics.csv
- traceability sample CSV: C:\Users\johnk\OneDrive\Desktop\project\sec_insight_rag\data\exports\ms2_5\metric_traceability_sample.csv

## Manual Judgment

This report presents evidence only. Review the report, database, and CSVs to
decide whether the observed behavior matches the Milestone 2.5 design.
