# AGENTS.md

## Project overview
This project is a backend-first financial research assistant that helps users understand company performance, risks, and possible drivers using SEC filings and XBRL financial data.

The system will ingest SEC filings and structured XBRL facts, calculate derived financial indicators, run deterministic financial analysis, retrieve relevant filing evidence, and generate retrieval-grounded language-model explanations. The main goal is to make financial analysis evidence-grounded, traceable, and easier to understand.

## Repository structure

- `config.env`: local environment variables, API keys, SEC user agent, and storage paths.
- `proposal.md`: project plan and MVP scope.
- `data/`: local sample data and immutable raw SEC fixtures used for testing.
- `data/fixtures/`: saved SEC API responses and filing samples for offline tests.
- `data/exports/`: generated CSV exports for raw facts and derived indicators.
- `data_store/filings/`: downloaded SEC filing documents.
- `storage/stock/`: local application storage for company facts, indicators, filing chunks, and retrieval indexes.
- `src/`: main backend source code.
- `src/config/`: environment loading and runtime settings.
- `src/api/`: FastAPI app, route definitions, request schemas, and response schemas.
- `src/ingestion/`: ticker-to-CIK lookup, SEC submissions retrieval, XBRL company facts retrieval, and filing download logic.
- `src/processing/`: XBRL normalization, unit handling, period alignment, and fact cleanup.
- `src/indicators/`: derived financial indicator formulas and source-fact traceability.
- `src/analytics/`: deterministic financial data analysis over raw facts and derived indicators, including trend analysis, period comparison, benchmark-ready analysis, and chart-ready output data.
- `src/retrieval/`: LlamaIndex-based document loading, text splitting, indexing, retrieval, filing chunk metadata, and retrieval pipeline.
- `src/analyze/`: RAG orchestration, Gemini calls, answer formatting, and final synthesis across raw facts, derived indicators, financial data analysis, and semantic filing evidence.
- `src/analyze/prompts.py`: the single source of truth for all prompt templates.
- `src/storage/`: SQLite repositories and local persistence helpers.
- `src/workflows/`: thin application workflow orchestration, such as company ingestion, that calls ingestion, processing, and storage modules without duplicating their logic.
- `src/evaluation/`: analysis-quality checks and evaluation scripts.
- `tests/`: unit and integration tests.
- `docs/`: design notes, API notes, and development documentation.
- `notebooks/`: exploratory analysis only; do not put production logic here.

Do not add v1 source folders for macro data, glossary data, graph storage, or frontend code unless the project scope changes.

## LLM and prompt rules

- Use `gemini-2.5-flash` as the default model for LLM reasoning, answer generation, and interpretation tasks.
- Do not introduce another LLM provider or model unless explicitly asked.
- Retrieval embeddings, deterministic parsing, SEC/XBRL normalization, and financial calculations should not depend on Gemini unless reasoning is required.
- Keep every LLM prompt template in `src/analyze/prompts.py`.
- Do not define prompt strings inline in API routes, ingestion code, retrieval code, or tests.
- Prompt templates should make the model separate reported facts, derived indicators, financial data analysis results, semantic filing analysis, and interpretations.
- Prompt templates should include financial data analysis results as a separate evidence source when available.
- Prompt templates should require evidence references and forbid unsupported causal claims.
- Use built-in LlamaIndex tools for non-reasoning pipeline tasks such as document loading, text splitting, indexing, retrieval, and embedding integration when available.
- Use `SentenceSplitter` as the default text splitter only when it fits the task.
- If a required non-reasoning task is not supported by a suitable built-in LlamaIndex tool, ask before adding custom tooling, a new library, or a separate external service.

## Coding Rules

### General Style
- Write simple, readable Python code.
- Prefer small functions with clear inputs and outputs.
- Add type hints for public functions and important internal functions.
- Use descriptive names for variables, functions, and classes.
- Avoid clever or overly abstract code unless it clearly reduces complexity.

### Safety and Configuration
- Do not hardcode file paths, API keys, credentials, or user-specific settings.
- Use environment variables or config files for secrets and external settings.
- Never commit secrets or credentials.
- Do not modify raw data files. Treat raw data as immutable.
- Do not introduce new dependencies unless necessary. If a new dependency is needed, explain why.

### Project Architecture
- Keep data ingestion, data processing, storage, retrieval, and analysis logic separate.
- Keep financial data analysis logic separate from Gemini/RAG synthesis logic.
- Do not use the LLM to calculate deterministic financial analysis results.
- Keep SEC API/client logic separate from database/repository logic.
- Keep data processing logic separate from retrieval/RAG logic.
- Keep workflow orchestration thin; workflows may call ingestion, processing, storage, retrieval, analytics, or analysis modules, but should not duplicate their internals.
- Treat `docs/structure.md` as the source of truth for the current repository and module structure.
- When a structural change is made, update `docs/structure.md` so it reflects the current system.
- Structural changes include adding, removing, renaming, or moving folders, source modules, important files, storage locations, tests, or module responsibilities.
- Do not change the database schema unless explicitly asked.
- Preserve public function names and existing interfaces unless explicitly asked.

### Before Coding
- Restate the task briefly.
- List important edge cases before implementation.
- Identify which files are likely to be changed.
- If the task affects architecture, schema, public APIs, or data integrity, ask for confirmation before changing.

### During Coding
- Make the smallest reasonable change that solves the task.
- Do not rewrite unrelated files.
- Do not refactor unrelated code.
- Do not silently swallow exceptions.
- Prefer explicit error handling over hidden failure.

### Testing
- Add or update tests for new behavior.
- Use mocked API responses when testing SEC/XBRL API logic.
- Run relevant tests after changes when possible.
- If tests fail, explain the failure before attempting a fix.

### After Coding
- Summarize every file changed and why.
- Explain any assumptions made.
- Explain any edge cases handled.
- Mention tests added or run.
- If the change affected repository structure, module responsibilities, important files, storage locations, or tests, mention that `docs/structure.md` was updated.

## Python style

- Follow PEP 8.
- Use `pandas` for local data processing.
- Use `pyspark` only when the task is explicitly about distributed processing.
- Use clear variable names.
- Add comments only when the logic is not obvious.
- Avoid over-engineering.
