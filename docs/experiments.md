# Experiment Runbook

## Purpose

Milestone experiments produce human-inspectable evidence for workflows that
unit tests alone cannot validate. They complement automated tests; they do not
replace them.

The corresponding milestone plan owns acceptance scenarios and required
evidence. This runbook owns only shared execution and artifact conventions.

## Core Rules

- Run experiments from the repository root with `uv run python ...`.
- Keep executable scripts under `experiments/MS#/`.
- Do not keep a separate `experiment_proposal.md`; acceptance design belongs in
  `docs/milestones/`.
- Prefer saved reports for detailed evidence and concise terminal summaries.
- Preserve source IDs, accession numbers, periods, warnings, and skip/failure
  reasons.
- Do not reduce evidence to a predeclared pass/fail label.
- Keep fixtures immutable.
- Keep generated databases, filings, reports, caches, and exports untracked.
- Never make a live SEC call without an identifying `SEC_USER_AGENT`.

## Data Modes

Use the smallest mode that answers the question:

- `fixture`: deterministic local data for repeatable behavior
- `local`: existing local database, filing, or index artifacts
- `live`: external SEC or model-provider calls

An experiment should label its mode, inputs, database, models, configuration,
and output paths. Live results are time-dependent and must not replace
deterministic automated coverage.

## Script Layout

```text
experiments/
  storage/                 generated shared experiment state
  MS2/
    ingestion_showcase.py
  MS3/
    mapping_inspection.py
  MS4/
    indicator_engine.py
  MS6/
    retrieval_pipeline.py
```

Create future milestone folders only when their experiments are designed and
implemented.

## Current Commands

```powershell
# MS2 deterministic SEC/XBRL ingestion showcase
# Fixture mode and a saved UTF-8 report are the defaults.
uv run python experiments/MS2/ingestion_showcase.py --ticker AAPL

# MS3 mapping inspection over local/live evidence
uv run python experiments/MS3/mapping_inspection.py --ticker AAPL

# MS4 indicator report from local stored metrics
uv run python experiments/MS4/indicator_engine.py --ticker AAPL

# MS6 filing retrieval inspection
uv run python experiments/MS6/retrieval_pipeline.py --ticker AAPL
```

Run each script with `--help` before relying on optional flags.

## Report Contract

A human-inspection report should include, when applicable:

- purpose and question
- run context and inputs
- selected filing/accession scope
- evidence inventory and coverage
- calculated/mapped/retrieved results
- source lineage
- warnings, skips, failures, and unavailable evidence
- timing and cache/reuse behavior
- artifact paths and reproduction command

Large tables belong in saved artifacts, not terminal output.

## Generated Artifacts

Typical local-only artifacts include:

- `experiments/storage/experiment.db`
- `experiments/storage/filings/`
- `experiments/MS2/ingestion_report_<TICKER>.txt`
- `experiments/MS3/mapping_report_*.md`
- `experiments/MS4/indicator_report_*.txt`
- `experiments/MS6/experiment_report_*.txt`
- generated CSV exports under `data/exports/`

`docs/structure.md` records authoritative artifact locations. Generated output
must not be treated as current evidence after producing code or inputs change;
regenerate it before review.

## Completion Evidence

The milestone plan records:

- exact automated and experiment commands
- inspected artifact locations
- acceptance results
- commits, pull requests, or tickets
- remaining limitations

A milestone is not completed solely because automated tests pass. Named
real-data or report-inspection gates must also be satisfied.
