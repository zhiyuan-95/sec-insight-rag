# Milestone 1 Experiment Proposal: Project Scaffold

## Purpose

This experiment should let a human inspect whether the backend scaffold exists,
settings can load, and the API health entrypoint can be created locally.

The experiment is not meant to deeply test every module. It should print the
basic project shape and runtime configuration that proves Milestone 1 is usable.

## Human Question

Can I see that the project has the expected backend scaffold, configuration
loading, and basic API health behavior?

## Milestone Scope

This experiment covers:

- required top-level folders
- configuration loading from `config.env`
- configured database and filings paths
- default LLM model setting
- FastAPI app creation
- health route behavior

This experiment does not cover SEC ingestion, XBRL normalization, storage,
retrieval, analytics, Gemini calls, or RAG answers.

## Recommended Location

```text
experiments/MS1/
  experiment_proposal.md
  milestone1_project_scaffold.py
```

## Data Modes

Use `local` mode only. This experiment should not contact SEC or Gemini.

## Input Cases

### Case 1: Normal Local Project Root

Command:

```text
python experiments/MS1/milestone1_project_scaffold.py
```

Purpose:

Show that the project root has the expected folders and that settings/API health
can be loaded.

### Case 2: Missing Or Unreadable Config

Command:

```text
python experiments/MS1/milestone1_project_scaffold.py --env-file missing.env
```

Purpose:

Show what the user sees when configuration is unavailable or incomplete.

## Proposed Terminal Report

```text
Milestone 1 Experiment: Project Scaffold

Human Question:
  Can I inspect the backend scaffold and basic runtime configuration?

Run Context:
  mode: local
  project root: <repo root>
  env file: config.env

Project Structure:
  src/: found
  tests/: found
  data/: found
  docs/: found
  experiments/: found

Configuration:
  config.env loaded: yes
  default LLM model: gemini-2.5-flash
  stock database path: stock_data.db
  filings directory: data_store/filings
  SEC user agent configured: yes/no
  Gemini key configured: yes/no

API:
  FastAPI app can be created: yes
  health route response: {"status": "ok"}

Artifacts To Inspect:
  source module: src/config/settings.py
  source module: src/api/main.py

Expected Outcome:
  Required folders exist, settings load without printing secrets, the default
  model is gemini-2.5-flash, and the health route can be created locally.

Manual Judgment:
  Confirm that the scaffold and runtime entrypoints look ready for later
  milestones.
```

## Required Printed Sections

1. Human question
2. Run context
3. Project structure
4. Configuration
5. API
6. Artifacts to inspect
7. Expected outcome
8. Manual judgment note

## Implementation Guidance

- Reuse `src/config/settings.py` for configuration loading.
- Reuse `src/api/main.py` for app creation.
- Do not print API keys, tokens, or raw credentials.
- Print whether sensitive values are configured, not their values.
- Keep the output short enough for a quick terminal inspection.

## Edge Cases To Show

- `config.env` is missing.
- required folder is missing.
- default model is not `gemini-2.5-flash`.
- FastAPI app cannot be created.
- health route is missing or returns an unexpected response.

## Expected Outcome

Milestone 1 looks healthy when the report lets the project owner answer:

- Does the expected backend folder structure exist?
- Can settings load locally?
- Is the default model pinned to `gemini-2.5-flash`?
- Are storage paths visible?
- Can the API app and health route be created?
