# Proposal: Evidence-Grounded Financial Thesis Engine

## 1. Project Goal

SEC Insight RAG is a backend-first financial research system that helps users understand company performance, risks, and possible drivers using SEC filings and XBRL financial data.

The system will ingest SEC filings and structured XBRL facts, calculate derived financial indicators, run deterministic financial analysis, retrieve relevant filing evidence, and generate retrieval-grounded language-model explanations. The main goal is to make financial analysis evidence-grounded, traceable, and easier to understand.

The first version will support one company ticker at a time and focus on recent 10-K and 10-Q filings and XBRL data extraction and processing.

This proposal defines product scope, architecture direction, and the MVP roadmap. It is not the live repository map; use `docs/structure.md` for implemented files, current module responsibilities, generated storage locations, and verification commands.

## 2. Core System Design

The target backend is organized around these main layers. Some are implemented and some remain planned:

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
   * Conditionally load active Inline XBRL and issuer-extension taxonomies when deterministic target coverage is incomplete.
   * Respect SEC fair-access rules with a configured `SEC_USER_AGENT`, throttling, and retry logic.
2. Financial data processing

   * Normalize XBRL facts by concept, period, unit, form type, and fiscal year/quarter.
   * Preserve Inline XBRL namespace, context, dimensions, consolidation state, and source-document lineage.
   * Store broad raw SEC/XBRL facts without modifying the original values.
   * Treat industry labels and target concept bundles as mapping/reporting inputs, not raw-ingestion filters.
   * Flag missing, duplicated, or ambiguous concepts instead of silently guessing.
3. Company inspection and base metric mapping

   * Store local company metadata, filing metadata, and update-check state.
   * Assign reusable hard industry labels from the latest 10-K Item 1 Business section with Gemini when configured, and reclassify when a newer 10-K changes the evidence.
   * Select target XBRL concept sets from common base candidates plus the industry-specific candidates for the company's approved hard labels.
   * Map selected raw XBRL facts into business-friendly base metrics grouped by financial statement type.
   * Run deterministic catalog mapping through catalog entries and approved global, industry, or company-scoped learned mappings.
   * Keep unresolved target coverage explicit instead of inferring a raw-concept mapping from similarity.
   * Generate report-only formula, zero-target, or no-evidence diagnostics from active-window raw facts for unresolved metrics; these diagnostics must not populate base metrics or approve mappings.
   * Reuse an approved company concept profile on later ingestions when it still covers the required target metrics.
   * Preserve traceability from each base metric back to the source raw XBRL fact and filing.
4. Derived indicator calculation

   * Calculate indicators from base financial metrics, including growth, margin, return, cash generation, liquidity, leverage, operating-efficiency, and shareholder-impact indicators.
   * Treat `free_cash_flow` as a derived indicator from operating cash flow and capital expenditure, not as a raw fact.
   * Store formulas and source fact references so each derived metric is auditable.
5. Financial data analysis

   * Analyze raw facts and derived indicators using deterministic data-analysis code before LLM synthesis.
   * Support analysis types such as historical trend analysis, period-over-period comparison, margin decomposition, volatility/outlier checks, and benchmark comparison when a reliable benchmark dataset is available.
   * Produce structured, chart-ready outputs that can later be visualized in a frontend or exported for review.
   * Keep the exact analysis library extensible because the most valuable analysis types will be refined through research.
6. Evidence retrieval

   * Chunk filing text from sections such as MD&A, Risk Factors, Business, financial statements, and notes.
   * Store chunk metadata including ticker, CIK, filing form, filing date, accession number, section, and source URL.
   * Use built-in LlamaIndex utilities for non-reasoning retrieval tasks such as document loading, text splitting, indexing, and retrieval when available.
7. LLM/RAG analysis and reasoning

   * Use Gemini for hard industry label classification and RAG reasoning, not for approving XBRL concept-to-metric mappings.
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
   * Current company ingestion orchestration lives in `src/ingestion/company.py`; add `src/workflows/company_ingestion.py` later only when a separate workflow boundary is useful.

## 3. LLM Usage and LlamaIndex Tooling Policy

For the current system, all LLM-based tasks will use `gemini-2.5-flash`. This keeps model behavior consistent, easier to debug, and easier to evaluate.

`gemini-2.5-flash` will be used for:

1. Hard industry classification

   * Classify a company into the fixed hard industry label set from the latest active 10-K Item 1 Business section.
   * Return strict JSON with labels, confidence, reason, and evidence quotes.
   * Reuse approved labels during the same annual filing cycle, and reclassify when a newer 10-K changes the source evidence.
   * Fall back to common-base target concepts when classification is unavailable, malformed, or low confidence; keep only supported high-confidence Gemini labels and ignore low-confidence labels without a human approval queue.
2. Query understanding

   * Convert user questions into retrieval intent.
   * Identify whether the user is asking about performance, risk, trend, comparison, or a specific financial metric.
3. Filing-text summarization

   * Summarize retrieved MD&A, Risk Factors, notes, or other filing sections.
   * Keep summaries grounded in retrieved text.
4. Evidence-grounded question answering

   * Combine structured metrics, derived indicators, financial data analysis results, and filing excerpts into a readable answer.
   * Cite the evidence used for each major claim.
5. Risk interpretation

   * Explain what indicators may suggest about liquidity, leverage, margin pressure, revenue decline, cash flow weakness, or business concentration.
   * Avoid claiming certainty unless explicitly supported by the filing.
6. Financial thesis generation

   * Generate a structured thesis with positive factors, negative factors, financial data analysis signals, semantic filing evidence, risks, open questions, and metrics to monitor.
7. Explanation refinement

   * Rewrite analysis in a clearer user-facing format while preserving evidence and labels.

Gemini output may propose hard industry labels, but it must not approve XBRL concept-to-system-metric mappings. Concept mappings require deterministic catalog entries or governed approved mapping records.

Non-reasoning pipeline tasks, such as document loading, text splitting, indexing, retrieval, and embedding integration, should use built-in LlamaIndex tools when available.

If a required non-reasoning task is not supported by a suitable built-in LlamaIndex tool, the implementer should ask before adding custom tooling, a new library, or a separate external service.

All prompt templates for Gemini should live in one dedicated source file, such as `src/analyze/prompts.py`. Application code should import prompt templates from that file instead of defining prompt strings inline.

For the MVP, the model-related configuration should be:

```env
PRIMARY_CHAT_MODEL=gemini-2.5-flash
ALLOWED_CHAT_MODELS=gemini-2.5-flash
```

Current configured services include:

* `Gemini_API_KEY` for Gemini-backed hard industry classification and LLM reasoning tasks.
* `SEC_USER_AGENT` for SEC data access.
* Storage path settings for local databases, filings, and knowledge indexes.
* Other API keys may remain in the config file for future expansion, but they are not required for the current MVP plan.

## 4. Data Storage

Use local storage for the MVP:

1. SQLite

   * Company metadata
   * Filing metadata
   * Raw XBRL facts
   * Reusable company hard industry labels and label evidence
   * Approved global, industry, and company-scoped XBRL concept mappings
   * Base financial metrics mapped from raw XBRL facts
   * Derived indicators
   * Financial data analysis results
   * Chart-ready analysis datasets
   * Filing chunks
   * Retrieval index generation state
   * Evidence references
   * Analysis outputs
2. Rebuildable retrieval indexes

   * Keep canonical filing chunks and source lineage in SQLite.
   * Use LlamaIndex-compatible local vector and keyword indexes as rebuildable retrieval artifacts for the MVP.
3. File storage

   * Save downloaded filings under the configured filings directory.
   * Save generated CSV files or produce them on demand from SQLite.

Configured paths should come from `config.env`, including:

* `STOCK_SQL_DB_PATH`
* `STOCK_STORAGE_BASE_DIR`
* `STOCK_FILINGS_BASE_DIR`
* `KNOWLEDGE_STORAGE_DIR`

Macro data, glossary data, and graph storage are not part of v1.

## 5. Backend API Plan

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

* `/ingest` calls company ingestion orchestration, retrieves SEC data, downloads filings, normalizes broad raw XBRL facts, assigns or reuses hard industry labels, maps approved base metrics, and stores traceability. Retrieval index synchronization remains an explicit separate operation until a later workflow or API integration connects it to ingestion.
* `/metrics` returns normalized base financial metrics.
* `/indicators` returns calculated financial indicators and formula references.
* `/analytics` returns deterministic financial data analysis results and chart-ready datasets.
* `/facts.csv` exports raw extracted facts.
* `/indicators.csv` exports derived indicators.
* `/analyze` generates a structured company analysis using raw facts, derived indicators, financial data analysis results, and semantic filing evidence.
* `/ask` answers a user question using RAG over SEC filing text, structured financial data, and financial data analysis results.

## 6. Evidence and Trust Rules

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
* Interpretation: The decline may be related to weaker demand if the MD&A section discusses lower sales volume.

## 7. MVP Milestones

1. Project scaffold

   * Create `src/`, `tests/`, `data/`, `docs/`, and configuration-loading structure.
   * Add dependency management and local run instructions.
2. SEC/XBRL ingestion and normalization

   * Implement ticker-to-CIK lookup.
   * Retrieve company submissions and companyfacts JSON.
   * Download latest 10-K and 10-Q filings.
   * Normalize broad raw SEC/XBRL facts for supported filing forms instead of limiting ingestion to the mapped concept catalog.
   * Normalize periods, units, fiscal years, and form types.
   * Store facts in SQLite.
200. Company registry, filing inventory, and base metric mapping

   * Add local company metadata, filing metadata, and update-check state.
   * Track latest ingested 10-K and 10-Q filing dates and next-check dates.
   * Keep `raw_xbrl_facts` as the source-of-truth table for normalized SEC/XBRL facts.
   * Supplement entity-wide companyfacts with issuer-extension and dimensional facts from active Inline XBRL filings.
   * Preserve links from each base metric back to the source filing and raw XBRL fact.
   * Do not calculate derived indicators in this milestone.
201. Industry-aware concept mapping

   * Persist reusable company hard industry labels and assignment evidence; use Gemini classification from latest 10-K Item 1 Business when configured.
   * Reuse approved labels during the same annual filing cycle and reclassify when a newer 10-K changes the label evidence.
   * Select the target XBRL concept set from common base candidates plus industry-specific candidates for every approved hard label.
   * Map selected raw XBRL facts into business-friendly base metrics by statement type through deterministic catalog entries and approved learned mappings.
   * Derive and reuse an approved company concept profile from approved global, industry, and company-scoped mappings.
202. Metric-first missing coverage resolution

   * Keep unresolved target XBRL concepts explicit after deterministic and approved learned mapping.
   * Generate report-only formula, zero-target, or no-evidence diagnostics from period-scoped active-window raw fact pools for unresolved metrics.
   * Present missing coverage as one internal-metric review surface rather than separate decisions for each target tag; report-only LLM diagnostics must not create base metrics or approve mappings.
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
   * Store canonical chunk metadata in SQLite and rebuildable local vector and keyword index artifacts under knowledge storage.
   * Reuse unchanged retrieval generations and preserve the last complete generation when a rebuild fails.
6. Gemini model integration

   * Load `gemini-2.5-flash` from configuration.
   * Use `gemini-2.5-flash` first for hard industry label classification from 10-K Item 1 Business during ingestion.
   * Use the same configured model for later LLM reasoning, summarization, Q&A, and thesis generation tasks.
   * Track model, provider, task type, latency, and token usage for each call.
7. RAG analysis

   * Combine retrieved filing chunks with structured metrics, derived indicators, and financial data analysis results.
   * Generate grounded answers and company thesis summaries.
8. FastAPI backend

   * Keep current ingestion orchestration usable through `src/ingestion/company.py`.
   * Add `src/workflows/company_ingestion.py` later if the API needs a separate thin workflow wrapper over ingestion, processing, storage, retrieval, analytics, or analysis modules.
   * Add ingestion, metrics, indicators, analytics, CSV export, analysis, and Q&A endpoints.
9. Testing and evaluation

    * Maintain focused automated tests for implemented deterministic behavior, repositories, public interfaces, regressions, and important failure paths.
    * Expand integration coverage as analytics, Gemini/RAG, workflows, and API routes are implemented.
    * Add sample expected outputs for analysis quality review.

## 8. Testing Plan

**Unit tests**:

* Environment configuration loading
* Gemini model configuration loading
* Rejection of unsupported chat models
* Ticker-to-CIK lookup
* SEC companyfacts parsing
* Arelle-backed Inline XBRL extension extraction
* XBRL concept normalization
* Gemini hard industry classification from 10-K Item 1 Business with strict label validation
* Hard industry label reuse, annual reclassification on a newer 10-K, and common-base fallback when Gemini labels are unavailable, invalid, or low confidence
* Target XBRL concept selection from common base plus approved hard industry labels
* Approved company concept profile reuse and staleness triggers
* Canonical missing-target detection through deterministic and approved learned mappings
* Rejection of report-only formula and zero-target diagnostics as stored metric sources
* Company, filing, and base metric repository behavior
* Raw XBRL fact to base metric mapping
* Derived indicator formulas, skipped reasons, source lineage, and persistence
* Financial data analysis calculations
* Chart-ready analytics output shape
* Filing HTML visibility cleanup and form-aware section detection
* Stable retrieval chunk identity and reciprocal-rank fusion
* Retrieval query validation, generation integrity, and evidence lineage
* CSV export formatting

**Integration tests**:

* Ingest one known ticker from saved SEC fixtures.
* Store normalized facts, filing metadata, hard industry labels, base metrics, and indicators in SQLite.
* With mocked Gemini output, confirm high-confidence labels change target concept selection and low-confidence output falls back to common-base targets.
* Confirm an approved company concept profile can be reused without unresolved-target provider calls when target coverage remains intact.
* Generate financial data analysis results from stored facts and indicators.
* Build, reuse, and safely replace retrieval generations while preserving the last complete generation after failures.
* Retrieve fused vector and BM25 evidence whose chunk IDs and lineage match canonical SQLite rows.
* Ask one performance question and confirm evidence references are included.
* Ask one risk question and confirm the answer uses cautious interpretation.

**Manual acceptance tests**:

* Run the MS200 experiment and inspect label source, target XBRL concept coverage, approved company concept profile reuse, unknown concepts, annual/quarterly mapped metric tables, and report-only formula/zero diagnostics.
* Run the MS3 experiment and inspect yearly and quarterly derived indicator tables with skipped reasons and source metric lineage.
* Run the MS5 retrieval experiment and inspect active filing coverage, chunk lineage, generation state, and retrieved evidence.
* Start the FastAPI backend.
* Ingest one company ticker.
* Export raw facts as CSV.
* Export derived indicators as CSV.
* Ask: "Why did revenue change?"
* Confirm the answer includes SEC evidence, calculated indicators, and no unsupported causal claims.

## 9. Local MVP Performance Expectations

Use these as initial review budgets on the current Windows development machine.
Experiments should record the measurements and supporting corpus size without
turning the report into an automatic pass/fail verdict.

* Reusing an ingested company when no SEC refresh is due: at most 10 seconds and no unnecessary SEC or filing download request.
* Reusing an unchanged retrieval generation for approximately 17 filings and 2,655 chunks: at most 2 seconds.
* Building the same retrieval corpus from scratch after the embedding model is cached: at most 120 seconds.
* First retrieval query in a new process: at most 15 seconds.
* Additional retrieval queries in the same process: at most 1 second each.
* Complete automated test suite: at most 60 seconds on the current repository baseline.

Investigate a budget when comparable local runs exceed it by more than 20% twice
in succession. Recalibrate deliberately when hardware, models, chunk settings,
or active-window corpus size changes.

## 10. Success Criteria

The MVP is successful if it can:

1. Ingest SEC filings and XBRL facts for one ticker.
2. Store broad raw XBRL facts separately from mapped base financial metrics.
3. Store company metadata, filing metadata, approved hard industry labels, and base financial metrics with source traceability.
4. Select target XBRL concepts from common base plus approved hard industry labels.
5. Reuse approved company concept profiles for normal refreshes and keep incomplete target coverage explicit.
6. Keep LLM formula and zero-target diagnostics report-only and out of stored base metrics and approved mappings.
7. Calculate and store useful financial indicators.
8. Run deterministic financial data analysis over raw facts and derived indicators.
9. Export raw facts and derived indicators as CSV.
10. Retrieve relevant filing evidence for user questions.
11. Use `gemini-2.5-flash` as the default LLM for hard industry classification, explanation, and analysis.
12. Use built-in LlamaIndex tools for non-reasoning retrieval pipeline tasks when available.
13. Produce answers that clearly distinguish fact, calculation, financial data analysis, semantic filing analysis, and interpretation.
14. Avoid unsupported causal claims.
15. Provide enough source references for users to verify the analysis.

## 11. Out of Scope for MVP

The first version will not include:

* Multi-company peer comparison
* Industry benchmark comparison until the benchmark dataset and peer/industry mapping are defined
* Portfolio-level screening
* Full frontend interface
* Real-time market data trading signals
* Investment recommendations
* Automatic buy/sell ratings
* Non-GAAP reconciliation beyond what is clearly available from filings
* Automatic approval of LLM-proposed XBRL mappings or formulas
* A broader industry taxonomy beyond the fixed hard industry label set

### Deferred indicator extensions

The core indicator catalog may later add ROIC, multi-year CAGR, accrual,
stock-based compensation, capital-return, composite-score, DuPont, margin-bridge,
and working-capital contribution indicators. Industry-specific indicators should
remain in separate, explicit catalogs or modules rather than being forced into
one universal catalog. Initial deferred families include bank, insurance, REIT,
and SaaS operating indicators.
