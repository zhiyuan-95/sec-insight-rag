# AGENTS.md

## Role of this file

This file is the project-level coding contract for AI coding agents.

It defines how agents should work in this repository: which sources to trust,
how to make changes, how to preserve architecture boundaries, how to use LLMs,
and how to report completed work.

Do not treat this file as the live repository map. For the current folder
layout, implemented modules, generated storage locations, and verification
workflow, read `docs/structure.md`.

## Repository-specific priority

For repository-specific guidance, use this order:

1. The user's direct request in the current task.
2. This `AGENTS.md` file.
3. `docs/structure.md` for current repository structure and implemented modules.
4. `proposal.md` for product goals, architecture direction, MVP scope, and milestones.
5. `docs/experiments.md` for experiment conventions and milestone experiment workflow.
6. `experiments/MS*/experiment_proposal.md` for milestone-specific experiment designs.
7. Historical plan files only as background context.

If repository documents conflict, stop and explain the conflict before making
changes that depend on the disputed instruction.

Historical milestone notes include `plan1.txt`, `plan2.txt`, `plan2.5.txt`,
`plan2.5.1.txt`, and `plan3.txt`. These files may explain past reasoning, but
they are not current structure truth.

## Project overview

SEC Insight RAG is a backend-first financial research system that helps users
understand company performance, risks, and possible drivers using SEC filings
and XBRL financial data.

The system ingests SEC filings and structured XBRL facts, calculates derived
financial indicators, runs deterministic financial analysis, retrieves relevant
filing evidence, and generates retrieval-grounded language-model explanations.

The main goal is to make financial analysis evidence-grounded, traceable, and
easier to understand.

The system should keep these evidence types distinct:

- Reported facts from SEC/XBRL sources.
- Base financial metrics.
- Derived financial indicators.
- Deterministic financial analysis results.
- Retrieved filing evidence.
- LLM-generated interpretations.

Unsupported causal claims are not allowed.

## Source-of-truth rules

- Use `docs/structure.md` for the current repository and module structure.
- Use `proposal.md` for product goals, architecture direction, MVP scope, and
  milestones.
- Use `docs/experiments.md` for experiment conventions and milestone experiment
  workflow.
- Use `experiments/MS*/experiment_proposal.md` for milestone-specific experiment
  designs.
- Treat historical plan files only as background context.
- Check `docs/structure.md` before making architecture-sensitive changes.
- If `proposal.md` and `docs/structure.md` disagree about current files or
  module responsibilities, treat `docs/structure.md` as current truth.
- Do not duplicate the full repository tree in this file.
- Do not assume planned modules are implemented. Verify current status in
  `docs/structure.md` and the filesystem.
- Do not treat generated files, local databases, downloaded filings, caches,
  virtual environments, or temporary experiment outputs as source architecture.

## Scope control

Do not add source folders, services, dependencies, or major modules outside the
current project scope unless explicitly requested.

Do not add v1 source folders for:

- Macro data.
- Glossary data.
- Graph storage.
- Frontend code.
- Multi-agent orchestration.
- External job queues.
- Cloud deployment infrastructure.

Prefer completing the current milestone cleanly over expanding the system.

## Interaction rules

When the task is ambiguous:

- Ask at most one clarification question at a time.
- Ask only when the ambiguity affects implementation, architecture, schema,
  public API behavior, data integrity, model/provider choice, or generated
  storage format.
- If a reasonable safe default exists, state the assumption and proceed.
- If the user asks for clarification about your question, answer only that
  clarification.
- If the user asks for a recommendation about your question, give the
  recommendation only.
- Do not move to the next design question until the user explicitly says to
  continue.
- Do not assume the user accepted a recommendation until they confirm it.

When discussing design before coding:

- Help the user discover the idea through focused questions.
- Prefer one concrete design question at a time.
- Separate product intent, data model, workflow behavior, edge cases, and
  implementation details.
- Do not jump into implementation before the design target is clear.

## Architecture boundaries

Keep these layers separate:

- SEC/API ingestion.
- XBRL normalization and cleanup.
- Storage and repositories.
- Retrieval.
- Deterministic financial calculations.
- Financial data analysis.
- Semantic filing analysis.
- LLM synthesis and interpretation.
- Workflow orchestration.

Rules:

- Keep SEC API/client logic separate from database/repository logic.
- Keep XBRL normalization and cleanup logic in processing code, not ingestion or
  storage code.
- Keep SQLite persistence in storage repositories and database helpers.
- Keep deterministic financial calculations out of Gemini/RAG synthesis.
- Keep financial data analysis logic separate from Gemini/RAG synthesis logic.
- Keep semantic filing retrieval separate from numeric financial analysis.
- Keep workflow orchestration thin.
- Workflows may call ingestion, processing, storage, retrieval, analytics, or
  analysis modules, but should not duplicate their internals.
- Preserve traceability between reported facts, base metrics, derived
  indicators, deterministic analysis, filing evidence, and LLM interpretations.
- Do not change the database schema unless explicitly asked.
- Preserve public function names and existing interfaces unless explicitly asked
  to change them.

## Data and evidence rules

- Do not present calculated values as reported facts.
- Do not present LLM interpretations as deterministic analysis.
- Do not make causal claims unless supported by financial data, filing evidence,
  or explicitly marked as a hypothesis.
- Preserve source references when moving data through the pipeline.
- Keep raw ingested data separate from cleaned, normalized, derived, or analyzed
  data.
- Treat raw data and fixtures as immutable unless the user explicitly asks to
  update a fixture.
- Do not modify downloaded SEC filings, raw XBRL payloads, local databases,
  caches, or generated artifacts unless the task specifically requires it.

## LLM and prompt rules

Use `gemini-2.5-flash` as the default model for LLM reasoning, answer
generation, and interpretation tasks.

Rules:

- Do not introduce another LLM provider or model unless explicitly asked.
- Retrieval embeddings, deterministic parsing, SEC/XBRL normalization, and
  financial calculations should not depend on Gemini unless reasoning is
  required.
- Keep every LLM prompt template in `src/analyze/prompts.py`.
- Do not define prompt strings inline in API routes, ingestion code, retrieval
  code, storage code, or workflows.
- Prompt templates should make the model separate reported facts, base metrics,
  derived indicators, financial data analysis results, semantic filing analysis,
  and interpretations.
- Prompt templates should include financial data analysis results as a separate
  evidence source when available.
- Prompt templates should require evidence references.
- Prompt templates should forbid unsupported causal claims.
- Prompt templates should require uncertainty language when evidence is
  incomplete.

## LlamaIndex rules

Use built-in LlamaIndex tools for non-reasoning pipeline tasks when they fit the
task.

Examples include document loading, text splitting, indexing, retrieval, and
embedding integration.

Rules:

- Use `SentenceSplitter` as the default text splitter only when it fits the
  task.
- Do not add custom retrieval, indexing, or chunking infrastructure unless
  built-in tools are insufficient.
- Ask before adding a new library, external service, or major custom tooling.
- Small local helper functions are allowed when they make the implementation
  simpler and do not introduce architectural complexity.

## Coding discipline

### General style

- Write simple, readable Python code.
- Follow PEP 8.
- Prefer small functions with clear inputs and outputs.
- Add type hints for public functions and important internal functions.
- Use descriptive names for variables, functions, and classes.
- Prefer `pandas` for local tabular data processing when it improves clarity.
- Use `pyspark` only when the task is explicitly about distributed processing.
- Avoid clever, overly abstract, or framework-heavy code unless it clearly
  reduces complexity.
- Add comments only when the logic is not obvious.
- Prefer explicit logic over hidden magic.

### Safety and configuration

- Do not hardcode file paths, API keys, credentials, or user-specific settings.
- Use environment variables or config files for secrets and external settings.
- Never commit secrets or credentials.
- Treat `config.env` as local configuration, not public documentation.
- Do not introduce new dependencies unless necessary.
- If a new dependency is needed, explain why.
- Do not silently swallow exceptions.
- Prefer explicit error handling over hidden failure.
- Avoid broad `except Exception` blocks unless they re-raise, log, or return a
  clearly documented failure result.

### Change discipline

- Make the smallest reasonable change that solves the task.
- Do not rewrite unrelated files.
- Do not refactor unrelated code.
- Do not rename files, functions, classes, modules, or public interfaces unless
  explicitly asked.
- Do not change database schema unless explicitly asked.
- Keep local docs synchronized with behavior when the task changes documented
  behavior.
- Respect user-owned notes and planning files; do not rewrite them unless the
  user asks.

## Before coding

Before implementation, briefly state:

- The task being performed.
- Important edge cases.
- Files likely to be changed.
- Assumptions.

Ask for confirmation before changing code when the task affects architecture,
database schema, public APIs, existing interfaces, data integrity, generated
storage format, model/provider choice, or repository structure.

If the task is small and unambiguous, proceed without unnecessary questions.

## During coding

- Keep the change focused.
- Prefer local changes over broad rewrites.
- Reuse existing utilities before adding new ones.
- Keep business logic out of API route handlers when possible.
- Keep storage logic inside repositories or database helpers.
- Keep prompt logic inside prompt modules.
- Keep workflows thin.
- Do not duplicate existing behavior.
- Update docs only when behavior, structure, or responsibilities change.

## Verification

This project does not maintain an automated `tests/` suite.

- Do not add pytest files or test-only dependencies unless the user explicitly
  changes the project testing policy.
- Prefer `uv run python ...` for local scripts and experiment runs.
- Use milestone experiments, terminal reports, generated SQLite databases, CSV
  exports, and downloaded filing artifacts for manual verification.
- When behavior is changed, explain what manual verification was performed or
  why it was not performed.

## Documentation rules

Update `docs/structure.md` when changes affect:

- Folder structure.
- Important files.
- Module responsibilities.
- Storage locations.
- Generated artifacts.
- Verification workflows.

Update `proposal.md` only when changes affect product goals, architecture
direction, MVP scope, or milestone intent.

Update `docs/experiments.md` only when changes affect experiment conventions,
experiment workflow, or experiment output expectations.

Do not rewrite historical planning files unless explicitly asked.

## Anti-overengineering rules

Avoid unnecessary complexity.

Do not add:

- New abstractions without repeated need.
- New dependencies for simple local logic.
- New services for local workflows.
- New configuration systems unless existing configuration is insufficient.
- New base classes unless multiple implementations already exist.
- New orchestration layers unless workflow complexity requires them.
- New prompt frameworks unless plain prompt templates are insufficient.
- New data stores unless SQLite/local files are insufficient for the current
  milestone.

Prefer clear functions, explicit data flow, small modules, traceable outputs,
deterministic calculations, and minimal moving parts.

## After coding

After implementation, summarize:

- Every file changed and why.
- Important implementation decisions.
- Assumptions made.
- Edge cases handled.
- Manual verification performed.
- Any verification not run and why.

If the change affected repository structure, module responsibilities, important
files, storage locations, generated artifacts, or verification workflows, mention
that `docs/structure.md` was updated.
