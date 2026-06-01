# Proposal: Evidence-Grounded Financial Thesis Engine

## 1\. Project Goal

This project is a backend-first financial research assistant that helps users understand company performance, risks, and possible drivers using SEC filings and XBRL financial data.

The system will ingest SEC filings and structured XBRL facts, calculate derived financial indicators, run deterministic financial analysis, retrieve relevant filing evidence, and generate retrieval-grounded language-model explanations. The main goal is to make financial analysis evidence-grounded, traceable, and easier to understand.

The first version will support one company ticker at a time and focus on recent 10-K\&10-Q filings and XBRL data extraction and processing.

## 2\. Core System Design

The backend will be organized into these main layers:

```text
src/
  config/
  api/
  ingestion/
  processing/
  indicators/
  analytics/
  retrieval/
  analyze/
  storage/
  workflows/
  evaluation/
```

1. Data ingestion

   * Resolve ticker symbols to SEC CIK identifiers.
   * Retrieve SEC company submissions and XBRL company facts.
   * Download relevant 10-K and 10-Q filing documents.
   * Respect SEC fair-access rules with a configured `SEC\\\\\\\_USER\\\\\\\_AGENT`, throttling, and retry logic.
2. Financial data processing

   * Normalize XBRL facts by concept, period, unit, form type, and fiscal year/quarter.
   * Store raw SEC facts without modifying the original values.
   * Flag missing, duplicated, or ambiguous concepts instead of silently guessing.
3. Company inspection and base metric mapping

   * Store local company metadata, filing metadata, and update-check state.
   * Map selected raw XBRL facts into business-friendly base metrics grouped by financial statement type.
   * Preserve traceability from each base metric back to the source raw XBRL fact and filing.
4. Derived indicator calculation

   * Calculate indicators from base financial metrics, such as revenue growth, gross margin, operating margin, net margin, current ratio, debt ratio, free cash flow, and cash conversion.
   * Store formulas and source fact references so each derived metric is auditable.
5. Financial data analysis

   * Analyze raw facts and derived indicators using deterministic data-analysis code before LLM synthesis.
   * Support analysis types such as historical trend analysis, period-over-period comparison, margin decomposition, volatility/outlier checks, and benchmark comparison when a reliable benchmark dataset is available.
   * Produce structured, chart-ready outputs that can later be visualized in a frontend or exported for review.
   * Keep the exact analysis library extensible because the most valuable analysis types will be refined through research.
6. Evidence retrieval

   * Chunk filing text from sections such as MD\&A, Risk Factors, Business, financial statements, and notes.
   * Store chunk metadata including ticker, CIK, filing form, filing date, accession number, section, and source URL.
   * Use built-in LlamaIndex utilities for non-reasoning retrieval tasks such as document loading, text splitting, indexing, and retrieval when available.
7. LLM/RAG analysis and reasoning

   * Use an LLM only after structured data, financial data analysis results, and relevant filing evidence have been retrieved.
   * Generate summaries, risk explanations, performance-driver analysis, and financial thesis outputs.
   * Clearly label each statement as a reported fact, derived indicator, financial data analysis result, semantic filing analysis, or interpretation.
   * Keep all Gemini prompt templates in one dedicated prompt file for easier review and maintenance.
8. Backend API

   * Expose the system through FastAPI.
   * Support ingestion, metrics lookup, financial data analysis lookup, thesis generation, question answering, and CSV export.
9. Application workflows

   * Provide user-facing orchestration functions for multi-step backend operations.
   * Keep orchestration thin by calling ingestion, processing, storage, retrieval, analytics, and analysis modules instead of duplicating their logic.
   * Start with `src/workflows/company_ingestion.py` for a single-company ingestion workflow.

## 3\. LLM Usage and LlamaIndex Tooling Policy

For the current system, all LLM-based tasks will use `gemini-2.5-flash`. This keeps model behavior consistent, easier to debug, and easier to evaluate.

`gemini-2.5-flash` will be used for:

1. Query understanding

   * Convert user questions into retrieval intent.
   * Identify whether the user is asking about performance, risk, trend, comparison, or a specific financial metric.
2. Filing-text summarization

   * Summarize retrieved MD\&A, Risk Factors, notes, or other filing sections.
   * Keep summaries grounded in retrieved text.
3. Evidence-grounded question answering

   * Combine structured metrics, derived indicators, financial data analysis results, and filing excerpts into a readable answer.
   * Cite the evidence used for each major claim.
4. Risk interpretation

   * Explain what indicators may suggest about liquidity, leverage, margin pressure, revenue decline, cash flow weakness, or business concentration.
   * Avoid claiming certainty unless explicitly supported by the filing.
5. Financial thesis generation

   * Generate a structured thesis with positive factors, negative factors, financial data analysis signals, semantic filing evidence, risks, open questions, and metrics to monitor.
6. Explanation refinement

   * Rewrite analysis in a clearer user-facing format while preserving evidence and labels.

Non-reasoning pipeline tasks, such as document loading, text splitting, indexing, retrieval, and embedding integration, should use built-in LlamaIndex tools when available.

If a required non-reasoning task is not supported by a suitable built-in LlamaIndex tool, the implementer should ask before adding custom tooling, a new library, or a separate external service.

All prompt templates for Gemini should live in one dedicated source file, such as `src/analyze/prompts.py`. Application code should import prompt templates from that file instead of defining prompt strings inline.

For the MVP, the model-related configuration should be:

```env
PRIMARY\\\\\\\_CHAT\\\\\\\_MODEL=gemini-2.5-flash
ALLOWED\\\\\\\_CHAT\\\\\\\_MODELS=gemini-2.5-flash
```

Current configured services include:

* `Gemini\\\\\\\_API\\\\\\\_KEY` for all LLM reasoning tasks.
* `SEC\\\\\\\_USER\\\\\\\_AGENT` for SEC data access.
* Storage path settings for local databases, filings, and knowledge indexes.
* Other API keys may remain in the config file for future expansion, but they are not required for the current MVP plan.

## 4\. Data Storage

Use local storage for the MVP:

1. SQLite

   * Company metadata
   * Filing metadata
   * Raw XBRL facts
   * Base financial metrics mapped from raw XBRL facts
   * Derived indicators
   * Financial data analysis results
   * Chart-ready analysis datasets
   * Filing chunks
   * Evidence references
   * Analysis outputs
2. Vector database

   * Store retrieval records for filing chunks.
   * Use LlamaIndex-compatible local retrieval/index storage for the MVP.
3. File storage

   * Save downloaded filings under the configured filings directory.
   * Save generated CSV files or produce them on demand from SQLite.

Configured paths should come from `config.env`, including:

* `STOCK\\\\\\\_SQL\\\\\\\_DB\\\\\\\_PATH`
* `STOCK\\\\\\\_STORAGE\\\\\\\_BASE\\\\\\\_DIR`
* `STOCK\\\\\\\_FILINGS\\\\\\\_BASE\\\\\\\_DIR`
* `KNOWLEDGE\\\\\\\_STORAGE\\\\\\\_DIR`

Macro data, glossary data, and graph storage are not part of v1.

## 5\. Backend API Plan

The MVP should expose these FastAPI routes:

```text
GET  /health
POST /companies/{ticker}/ingest
GET  /companies/{ticker}/metrics
GET  /companies/{ticker}/indicators
GET  /companies/{ticker}/analytics
GET  /companies/{ticker}/facts.csv
GET  /companies/{ticker}/indicators.csv
POST /companies/{ticker}/analyze
POST /companies/{ticker}/ask
```

Expected behavior:

* `/ingest` calls the company ingestion workflow, retrieves SEC data, downloads filings, normalizes XBRL facts, stores normalized raw facts, and later can trigger filing chunking and retrieval index updates when the retrieval milestone is implemented.
* `/metrics` returns normalized base financial metrics.
* `/indicators` returns calculated financial indicators and formula references.
* `/analytics` returns deterministic financial data analysis results and chart-ready datasets.
* `/facts.csv` exports raw extracted facts.
* `/indicators.csv` exports derived indicators.
* `/analyze` generates a structured company analysis using raw facts, derived indicators, financial data analysis results, and semantic filing evidence.
* `/ask` answers a user question using RAG over SEC filing text, structured financial data, and financial data analysis results.

## 6\. Evidence and Trust Rules

Every generated answer should follow these rules:

1. Separate facts, calculations, financial data analysis results, semantic filing analysis, and interpretations.
2. Include evidence references for important claims.
3. Do not state causality unless the filing explicitly supports it.
4. Prefer phrases such as "may indicate", "suggests", or "is consistent with" when interpreting risk.
5. Show the metric period, filing form, and source where possible.
6. If evidence is weak or missing, say so directly.
7. If XBRL data is incomplete or ambiguous, return a warning instead of inventing a value.

Example distinction:

* Reported fact: Revenue declined from one period to another based on SEC XBRL data.
* Derived indicator: Revenue growth was negative based on the calculated period-over-period formula.
* Financial data analysis result: Revenue growth was below the selected benchmark or historical average if a reliable comparison dataset is available.
* Interpretation: The decline may be related to weaker demand if the MD\&A section discusses lower sales volume.

## 7\. MVP Milestones

1. Project scaffold

   * Create `src/`, `tests/`, `data/`, `docs/`, and configuration-loading structure.
   * Add dependency management and local run instructions.
2. SEC/XBRL ingestion and normalization

   * Implement ticker-to-CIK lookup.
   * Retrieve company submissions and companyfacts JSON.
   * Download latest 10-K and 10-Q filings.
   * Extract common GAAP financial concepts.
   * Normalize periods, units, fiscal years, and form types.
   * Store facts in SQLite.
   * Add `src/workflows/company_ingestion.py` as the orchestration wrapper that calls existing ingestion, processing, and storage functions without duplicating their logic.
2.5. Company registry, filing inventory, and base metric mapping

   * Add local company metadata, filing metadata, and update-check state.
   * Track latest ingested 10-K and 10-Q filing dates and next-check dates.
   * Keep `raw_xbrl_facts` as the source-of-truth table for normalized SEC/XBRL facts.
   * Map selected raw XBRL facts into business-friendly base metrics by statement type.
   * Preserve links from each base metric back to the source filing and raw XBRL fact.
   * Do not calculate derived indicators in this milestone.
3. Indicator engine

   * Calculate core financial indicators from base financial metrics.
   * Store indicator formulas and source fact references.
4. Financial data analysis

   * Add a modular analysis layer for deterministic analysis of raw facts and derived indicators.
   * Start with historical trend and period-over-period analysis.
   * Add industry-average or benchmark comparisons only after the benchmark source and peer/industry mapping are defined.
   * Return structured findings and chart-ready data for later visualization.
5. Retrieval pipeline

   * Parse and chunk filing text.
   * Use built-in LlamaIndex tools for document loading, text splitting, indexing, and retrieval when available.
   * Store chunk metadata and vector index records.
6. Gemini model integration

   * Load `gemini-2.5-flash` from configuration.
   * Use `gemini-2.5-flash` for all current LLM reasoning, summarization, Q\&A, and thesis generation tasks.
   * Track model, provider, task type, latency, and token usage for each call.
7. RAG analysis

   * Combine retrieved filing chunks with structured metrics, derived indicators, and financial data analysis results.
   * Generate grounded answers and company thesis summaries.
8. FastAPI backend

   * Add ingestion, metrics, indicators, analytics, CSV export, analysis, and Q\&A endpoints.
9. Testing and evaluation

    * Add unit tests for parsing, normalization, formulas, and routing.
    * Add integration tests for one known ticker.
    * Add sample expected outputs for analysis quality review.

## 8\. Testing Plan

\*\*Unit tests\*\*:

* Environment configuration loading
* Gemini model configuration loading
* Rejection of unsupported chat models
* Ticker-to-CIK lookup
* SEC companyfacts parsing
* XBRL concept normalization
* Company, filing, and base metric repository behavior
* Raw XBRL fact to base metric mapping
* Derived indicator formulas
* Financial data analysis calculations
* Chart-ready analytics output shape
* CSV export formatting

\*\*Integration tests\*\*:

* Ingest one known ticker from saved SEC fixtures.
* Store normalized facts, filing metadata, base metrics, and indicators in SQLite.
* Generate financial data analysis results from stored facts and indicators.
* Build retrieval chunks using built-in LlamaIndex utilities.
* Ask one performance question and confirm evidence references are included.
* Ask one risk question and confirm the answer uses cautious interpretation.

\*\*Manual acceptance tests\*\*:

* Start the FastAPI backend.
* Ingest one company ticker.
* Export raw facts as CSV.
* Export derived indicators as CSV.
* Ask: "Why did revenue change?"
* Confirm the answer includes SEC evidence, calculated indicators, and no unsupported causal claims.

## 9\. Success Criteria

The MVP is successful if it can:

1. Ingest SEC filings and XBRL facts for one ticker.
2. Store company metadata, filing metadata, and base financial metrics with source traceability.
3. Calculate and store useful financial indicators.
4. Run deterministic financial data analysis over raw facts and derived indicators.
5. Export raw facts and derived indicators as CSV.
6. Retrieve relevant filing evidence for user questions.
7. Use `gemini-2.5-flash` as the default LLM for explanation and analysis.
8. Use built-in LlamaIndex tools for non-reasoning retrieval pipeline tasks when available.
9. Produce answers that clearly distinguish fact, calculation, financial data analysis, semantic filing analysis, and interpretation.
10. Avoid unsupported causal claims.
11. Provide enough source references for users to verify the analysis.

## 10\. Out of Scope for MVP

The first version will not include:

* Multi-company peer comparison
* Industry benchmark comparison until the benchmark dataset and peer/industry mapping are defined
* Portfolio-level screening
* Full frontend interface
* Real-time market data trading signals
* Investment recommendations
* Automatic buy/sell ratings
* Non-GAAP reconciliation beyond what is clearly available from filings

These can be added after the backend evidence pipeline is reliable.
