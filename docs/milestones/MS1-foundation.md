# MS1 — Foundation and Configuration

## Status

`completed`

This plan preserves the accepted foundation contract from the original
foundation design.

## Purpose and Deliverable

Establish a local Python backend with dependency management, configuration
loading, a minimal FastAPI application, a health endpoint, package boundaries,
and automated tests. This milestone creates the scaffold used by later SEC,
XBRL, indicator, retrieval, and LLM capabilities without implementing those
capabilities itself.

## Scope

- Manage dependencies and project metadata through `pyproject.toml` and `uv`.
- Load local configuration without hardcoding credentials or user paths.
- Expose a minimal FastAPI application and `GET /health`.
- Establish the source, test, data, documentation, and experiment layout.
- Keep prompt templates under `src/analyze/prompts.py`.
- Provide local setup, run, and test commands.

## Non-Goals

- SEC network calls or filing ingestion
- XBRL normalization or database schema design
- Financial metrics or indicators
- Filing retrieval, embeddings, or indexes
- Gemini or another LLM call
- Frontend or deployment infrastructure

## Accepted Decisions and Invariants

- Python 3.11 or later and `uv` are the local runtime conventions.
- Secrets and machine-specific settings remain in ignored environment files.
- Missing SEC or Gemini credentials do not block application startup; the
  capability that needs a credential validates it at its own boundary.
- API route handlers remain thin and do not absorb business or storage logic.
- Prompt strings do not live in routes, ingestion, retrieval, or storage code.

## Important Interfaces

- `src/config/settings.py` owns settings loading.
- `src/api/main.py` owns application creation and the health route.
- `src/analyze/prompts.py` owns prompt templates as later milestones add them.
- `uv run python -m pytest -q` is the standard complete automated-test command.

## Failure Behavior

- Configuration errors identify the missing or malformed setting.
- A missing optional external-service credential fails only when that service is
  invoked.
- The health endpoint does not contact SEC, model providers, or other external
  services.

## Acceptance Criteria

- The project installs through `uv`.
- Settings load from supported environment sources without committed secrets.
- The FastAPI application starts.
- `GET /health` reports healthy status.
- Focused settings and health tests pass.
- Local setup and verification commands are documented.

## Completion Evidence

The current repository contains the configured package structure, settings
loader, FastAPI application, health route, and automated settings/health tests.
Current runtime details and commands are recorded in `docs/structure.md` and
`README.md`.
