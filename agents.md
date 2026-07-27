# AGENTS.md

## Purpose

This file is the coding contract for AI agents working in SEC Insight RAG. It
defines authority, boundaries, safety, implementation, verification, and
reporting rules. It is not the repository map.

## Authority Order

For repository-specific decisions, use:

1. The user's current request
2. This agent contract
3. `docs/structure.md` for implemented runtime truth
4. `docs/milestones/README.md` and the owning milestone plan for approved design
5. `docs/policies/` for durable mechanisms
6. `proposal.md` for overall direction and roadmap
7. `docs/experiments.md` for shared experiment conventions
8. Git history for superseded designs

`CONTEXT.md` owns canonical domain terminology. If authoritative documents
conflict, stop and explain the conflict before making a dependent change.

Do not treat generated files, local databases, downloaded filings, caches,
virtual environments, reports, or temporary outputs as source architecture.

## Product and Evidence Boundaries

SEC Insight RAG ingests SEC evidence, maps base metrics, calculates deterministic
financial results, retrieves filing passages, and produces evidence-grounded
interpretations.

Keep distinct:

- reported SEC/XBRL facts
- base financial metrics
- derived indicators
- deterministic financial analysis
- retrieved filing evidence
- LLM-generated interpretation

Never present a calculated value as reported, an LLM interpretation as
deterministic analysis, or an unsupported hypothesis as causation. Preserve
source lineage through every layer and state uncertainty when evidence is weak.

## Scope Control

Do not add major services, dependencies, schemas, or source areas unless the
request requires them. The initial project excludes:

- frontend code
- macro-data ingestion
- graph storage
- multi-agent runtime orchestration
- external queues
- cloud deployment infrastructure

Prefer the smallest change that completes the active milestone contract.

## Interaction

Before implementation, state the task, important edge cases, likely changed
files, and assumptions.

Ask at most one clarification question at a time, and only when the answer
affects architecture, schema, public interfaces, data integrity, model choice,
or generated-storage format. If a safe default exists, state it and proceed.

During design discussions:

- resolve one decision at a time
- distinguish product intent, domain language, workflow, data contracts,
  edge cases, and implementation
- do not treat a recommendation as accepted until the user confirms it
- do not implement before the design is sufficiently resolved

## Architecture

Keep these layers separate:

- SEC/API ingestion
- XBRL normalization, reconciliation, and mapping
- storage repositories
- deterministic indicators and financial analysis
- filing parsing and retrieval
- LLM synthesis
- API and workflow orchestration

Rules:

- SEC clients do not write databases.
- Processing code owns XBRL cleanup, precedence, mapping, and deterministic
  transformation.
- SQLite access remains in repositories and database helpers.
- Deterministic calculations do not depend on Gemini or another LLM.
- Numeric analysis and filing-text retrieval remain separate evidence sources.
- Workflows coordinate layers without copying their internals.
- Preserve public interfaces unless the user approves a change.
- Do not change the database schema without explicit approval.

## Data Safety

- Raw fixtures and downloaded SEC evidence are immutable unless explicitly in
  scope.
- Keep raw observations separate from normalized, mapped, derived, or analyzed
  state.
- Preserve accession, period, source, and evidence references.
- Do not silently guess missing, ambiguous, malformed, or conflicting values.
- Keep generated caches and indexes rebuildable.
- Do not hardcode credentials, user-specific paths, or API keys.
- Treat `config.env` as local configuration.
- Never commit secrets.

## Models and Prompts

Use the model choices approved by the owning milestone or policy. Current
project defaults are:

- `gemini-3.1-flash-lite` for fiscal-period industry classification
- the MS3 three-judge lineup defined in `docs/policies/mapping.md`
- `gemini-2.5-flash` for general explanation and analysis

Do not introduce another provider or change a model contract without approval.

Every prompt template belongs in `src/analyze/prompts.py`. Prompts must:

- distinguish facts, metrics, indicators, deterministic analysis, retrieved
  evidence, and interpretation
- require evidence references
- forbid unsupported causal claims
- require uncertainty language when evidence is incomplete

Retrieval loading, splitting, indexing, embedding, and parsing should not depend
on LLM reasoning. Prefer fitting built-in LlamaIndex tools over new custom
infrastructure.

## Coding Discipline

- Write simple, readable, typed Python.
- Follow PEP 8.
- Prefer small functions with clear inputs and outputs.
- Reuse existing utilities and repositories.
- Keep business logic out of API routes.
- Keep prompt text out of routes, ingestion, retrieval, storage, and workflows.
- Prefer explicit error handling; do not silently swallow failures.
- Avoid broad `except Exception` unless it logs, re-raises, or returns a clearly
  documented failure.
- Add comments only where intent is not obvious.
- Do not add a dependency for simple local behavior.
- Do not create abstractions, base classes, services, or configuration systems
  without repeated need.

## Change Discipline

- Preserve user-owned and unrelated work in a dirty tree.
- Make the smallest complete change.
- Do not refactor, rename, or rewrite unrelated code.
- Do not alter public interfaces or schemas without approval.
- Keep docs synchronized when responsibilities, behavior, artifacts, or
  verification workflows change.
- Keep completed canonical milestone plans; remove obsolete drafts only after
  migrating unique durable content.
- Preserve superseded versions in Git history, not an active archive.

## Verification

Automated tests and milestone experiments serve different purposes.

- Add focused tests for deterministic behavior, repositories, public
  interfaces, regressions, and failure paths.
- Use milestone experiments for real filing/report inspection and end-to-end
  evidence.
- Prefer `uv run python ...`.
- Do not add another test framework or test-only dependency without approval.
- Do not call a milestone completed from green unit tests alone when its plan
  requires real-data or report acceptance.
- Report every check run and every relevant check not run.

## Documentation Ownership

- `proposal.md`: project direction, architecture intent, and roadmap
- `CONTEXT.md`: domain glossary only
- `docs/structure.md`: current implemented repository truth
- `docs/milestones/`: one high-fidelity plan per designed milestone
- `docs/policies/`: durable cross-milestone mechanisms
- `docs/experiments.md`: shared experiment runbook
- GitHub issues: implementation tasks
- Git history: obsolete drafts and superseded versions

A milestone plan may name contract-relevant modules, interfaces, records, and
tables. It should not maintain exhaustive file-edit lists or ticket-by-ticket
work logs.

Update:

- `docs/structure.md` when implemented modules, ownership, storage, generated
  artifacts, or verification workflows change
- `proposal.md` when overall direction, roadmap, or scope changes
- the owning milestone when its accepted design, status, or completion evidence
  changes
- a policy when its durable mechanism changes

## Completion Report

After implementation, summarize:

- every changed file and why
- important decisions and assumptions
- edge cases handled
- automated and manual verification
- checks not run and why
- documentation updated

Do not claim completion while required work or acceptance evidence remains.
