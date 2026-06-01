# Financial Research Assistant

Backend-first financial research assistant for evidence-grounded analysis of SEC filings and XBRL financial data.

## Local Setup

Install dependencies with `uv`:

```powershell
uv sync
```

Run the test suite:

```powershell
uv run pytest
```

Start the local FastAPI backend:

```powershell
uv run uvicorn src.api.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/health
```

## Configuration

Local settings are read from `config.env`. This file may contain secrets, so do not commit real API keys or credentials.

The FastAPI app shell can start without calling SEC, Gemini, LlamaIndex, or any external service. Live SEC ingestion helpers require `SEC_USER_AGENT`.

Expected local variables include:

```env
Gemini_API_KEY=
SEC_USER_AGENT=
STOCK_SQL_DB_PATH=stock_data.db
STOCK_STORAGE_BASE_DIR=./storage/stock
STOCK_FILINGS_BASE_DIR=./data_store/filings
KNOWLEDGE_STORAGE_DIR=
PRIMARY_CHAT_MODEL=gemini-2.5-flash
ALLOWED_CHAT_MODELS=gemini-2.5-flash
```

## Current Scope

Implemented so far:

- Backend package scaffold
- Typed settings loader
- FastAPI app factory
- `GET /health`
- Unit tests for settings and health checks
- SEC ticker-to-CIK lookup helpers
- SEC submissions and companyfacts retrieval helpers
- Latest 10-K/10-Q filing selection and primary document download helpers
- XBRL companyfacts normalization into raw fact records
- SQLite storage for normalized raw XBRL facts
- Unit tests for ingestion, normalization, and raw fact persistence

- `ingest_company(...)` exported from `src.ingestion` to orchestrate ticker resolution, SEC retrieval, filing downloads, XBRL normalization, and SQLite persistence

Not implemented yet:

- Derived indicators
- Deterministic analytics
- LlamaIndex retrieval
- Gemini model calls
- RAG analysis
- CSV export routes
