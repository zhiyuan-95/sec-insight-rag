# Milestone 2 Experiment Proposal: SEC/XBRL Ingestion And Normalization

## Purpose

This experiment should let a human inspect whether Milestone 2 works in the
most intuitive way: choose a company, run ingestion, then look at what filings
and normalized XBRL facts the system produced.

The experiment is not primarily a pass/fail test. It should print a concise
terminal report that shows the main artifacts created by the ingestion layer so
the project owner can judge whether the system behavior matches the project
design.

## Human Question

If I ask the current system to ingest one company, can I see:

- which company was resolved from the ticker
- how many 10-K years were selected or ingested
- how many 10-Q quarters were selected or ingested
- where the downloaded 10-K and 10-Q files are stored
- which normalized XBRL object/table stores the extracted facts
- which XBRL concepts were stored for the company
- what the first rows of the stored raw XBRL fact table look like

## Milestone Scope

This experiment covers only Milestone 2 behavior:

- ticker-to-CIK resolution
- SEC submissions retrieval or fixture loading
- SEC companyfacts retrieval or fixture loading
- latest 10-K and 10-Q filing selection
- filing document download or fixture document creation
- XBRL fact normalization for the common `us-gaap` concept list in 10-K and 10-Q facts
- raw normalized fact storage in SQLite
- top-row inspection of the raw fact table

This experiment does not cover Milestone 2.5 company registry behavior, active
window management, base metric mapping, derived indicators, analytics,
retrieval, Gemini integration, or RAG answers.

## Recommended Location

The runnable script for this proposal should live under the Milestone 2
experiment folder:

```text
experiments/MS2/
  experiment_proposal.md
  milestone2_ingestion_showcase.py
```

The script name can change, but it should stay inside `experiments/MS2/` so all
Milestone 2 experiment design and execution files are grouped together.

## Data Modes

The experiment should support two modes:

```text
fixture
  Uses saved SEC sample payloads under data/fixtures/.
  Does not contact SEC.
  Best for repeatable supervision.

live
  Contacts SEC using the configured SEC user agent.
  Downloads real filing documents into the configured filings directory.
  Best for checking real ingestion behavior.
```

Default mode should be `fixture`. Live mode should be explicit because SEC data,
network availability, and filing contents can change.

## Input Cases

### Case 1: Supported Fixture Company

Command:

```text
python experiments/MS2/milestone2_ingestion_showcase.py --ticker AAPL --mode fixture
```

Purpose:

Show the complete Milestone 2 ingestion flow using stable saved data.

Expected human inspection:

- ticker resolves to Apple's CIK
- at least one 10-K and one 10-Q are selected from fixture data
- filing paths are printed
- `raw_xbrl_facts` is printed as the storage table
- top rows from `raw_xbrl_facts` are visible
- duplicate or ambiguous facts show quality flags instead of being hidden

### Case 2: Unsupported Fixture Company

Command:

```text
python experiments/MS2/milestone2_ingestion_showcase.py --ticker MSFT --mode fixture
```

Purpose:

Show that fixture mode is limited to companies with saved fixture payloads.

Expected human inspection:

- the report explains that fixture mode currently supports only saved fixture
  tickers
- the script does not pretend that MSFT fixture data exists
- no live SEC call is made

### Case 3: Live SEC Company

Command:

```text
python experiments/MS2/milestone2_ingestion_showcase.py --ticker AAPL --mode live
```

Purpose:

Show the real SEC ingestion behavior using the configured local environment.

Expected human inspection:

- SEC user agent is loaded from configuration without printing secrets
- real filing paths under the configured filings directory are printed
- the database path is printed
- the top five stored rows reflect the live SEC companyfacts payload

## Proposed Terminal Report

The experiment should print a report like this:

```text
Milestone 2 Experiment: SEC/XBRL Ingestion And Normalization

Human Question:
  If I ingest a company, can I inspect filing counts, filing locations,
  normalized XBRL storage, and sample stored rows?

Run Context:
  mode: fixture
  ticker: AAPL
  cik: 0000320193
  database: <temporary fixture db or configured local db>
  filings directory: <temporary fixture filings dir or configured local dir>

Company Resolution:
  ticker  cik         company name
  AAPL    0000320193  Apple Inc.

Filing Period Coverage:
  form   periods represented   filings selected
  10-K   1 fiscal year         1
  10-Q   1 fiscal quarter      1

Selected Filings:
  form   filing date   report date   accession number      primary document
  10-K   2023-11-03    2023-09-30    0000320193-23-000106  aapl-20230930.htm
  10-Q   2024-02-02    2023-12-30    0000320193-24-000006  aapl-20231230.htm

Downloaded Filing Paths:
  form   local path
  10-K   data_store/filings/0000320193/0000320193-23-000106/aapl-20230930.htm
  10-Q   data_store/filings/0000320193/0000320193-24-000006/aapl-20231230.htm

XBRL Normalization:
  normalized object: NormalizedFact
  storage table: raw_xbrl_facts
  taxonomy filter: us-gaap
  concept filter: common us-gaap concept list
  form filter: 10-K, 10-Q
  normalized fact count: 5
  stored row count: 4
  distinct concepts ingested: 2
  quality flags observed: ambiguous_unit, duplicate_fact

XBRL Concepts Stored In Database:
  Income statement:
  taxonomy  concept   stored rows  forms       units
  us-gaap   Revenues  2            10-K, 10-Q  USD

  Balance sheet:
  taxonomy  concept   stored rows  forms       units
  us-gaap   Assets    2            10-K        EUR, USD

Top 5 raw_xbrl_facts Rows:
  id  cik         concept   unit  fiscal_year  fiscal_period  form  value
  1   0000320193  Assets    USD   2023         FY             10-K  ...
  2   0000320193  Revenues  USD   2023         FY             10-K  ...
  3   0000320193  Assets    USD   2024         Q1             10-Q  ...
  4   0000320193  Revenues  USD   2024         Q1             10-Q  ...

Artifacts To Inspect:
  filing directory: <printed filings directory>
  database table: raw_xbrl_facts
  source modules: src/ingestion/, src/processing/xbrl_normalizer.py,
                  src/storage/facts_repository.py

Expected Outcome:
  The report should make it easy to inspect annual and quarterly filing
  ingestion, downloaded filing locations, normalized XBRL storage, and stored
  fact rows.

Manual Judgment:
  Compare the observed report with this proposal. The project owner decides
  whether the milestone behavior looks correct.
```

## Required Printed Sections

The runnable experiment should print these sections in this order:

1. Human question
2. Run context
3. Company resolution
4. Filing period coverage
5. Selected filings
6. Downloaded filing paths
7. XBRL normalization summary
8. XBRL concepts stored in database, grouped by financial statement sector
9. Top five `raw_xbrl_facts` rows
10. Artifacts to inspect
11. Expected outcome
12. Manual judgment note

## Implementation Guidance

The runnable experiment should reuse project modules instead of duplicating
business logic:

- use ticker resolution from `src/ingestion/tickers.py`
- use submissions retrieval from `src/ingestion/submissions.py`
- use companyfacts retrieval from `src/ingestion/companyfacts.py`
- use filing selection/download logic from `src/ingestion/filings.py`
- use normalization from `src/processing/xbrl_normalizer.py`
- use SQLite helpers and raw fact repository from `src/storage/`

Fixture mode may patch SEC access functions to read saved payloads, but it
should still call the same ingestion, normalization, and storage behavior that
the real system uses.

Default normalization should store the common `us-gaap` concept list for 10-K
and 10-Q forms. Non-`us-gaap` taxonomies and non-10-K/10-Q forms remain out of
scope for Milestone 2.

## Storage To Inspect

The main database artifact is:

```text
raw_xbrl_facts
```

The top-five preview should include only columns that help human inspection,
such as:

- row id
- CIK
- taxonomy
- concept
- unit
- fiscal year
- fiscal period
- form
- filing date
- accession number
- numeric value
- quality flags

The concept summary should print every XBRL concept stored for the company in
`raw_xbrl_facts`, grouped by financial statement sector, including taxonomy,
concept name, stored row count, forms, and units. This should not be truncated
into only a few example concepts. Supported sector headings include income
statement, balance sheet, cash flow statement, EPS and shares, other
comprehensive income, and unmapped financial facts.

The main file artifact is:

```text
data_store/filings/
```

In fixture mode, the script may use a temporary filings directory, but it should
still print the exact directory and file paths.

## Edge Cases To Show

The experiment should make these situations visible:

- fixture ticker is unsupported
- SEC user agent is missing in live mode
- no 10-K is selected
- no 10-Q is selected
- filing document path is missing
- no normalized facts are produced
- normalized facts exist but no rows are stored
- duplicate facts are upserted into fewer stored rows
- ambiguous units or duplicate facts are represented through quality flags

The experiment should not hide these cases behind only a final result label.
It should print the available observed evidence so the project owner can judge
what happened.

## Expected Outcome

Milestone 2 looks healthy when the printed report lets the project owner answer:

- Which CIK did this ticker resolve to?
- How many annual 10-K periods were represented?
- How many quarterly 10-Q periods were represented?
- Which filing files can I open locally?
- Which XBRL concepts were normalized?
- Which XBRL concepts were stored in `raw_xbrl_facts` for this company?
- Which financial statement sector does each stored concept belong to?
- Which database table stores the normalized facts?
- Do the first stored rows look like real SEC/XBRL facts?
- Are duplicate or ambiguous facts visible through quality flags?

If those questions can be answered from the terminal report, the experiment is
serving its supervision purpose.
