# Experiment Runbook

## Purpose

This runbook defines the shared philosophy and location rules for milestone
experiments. The explicit design for each milestone belongs in that milestone's
own proposal file under `experiments/`.

Use this file as the central index. Use the milestone proposal files for the
actual experiment design.

## Core Rule

```text
Experiments demonstrate.
Milestone proposal files define exactly what to print and inspect.
Manual review is the verification path.
```

An experiment is a runnable, human-readable showcase of one milestone's main
functionality. It should mimic the way the project owner naturally inspects that
stage through a saved report and a concise terminal summary:

```text
I try the important user action.
I save what the system found or created in a human-readable report.
I inspect counts, paths, dates, table names, and sample rows in that report.
I try alternate cases when the milestone has branch behavior.
I decide whether the behavior looks right.
```

## File Layout

Put detailed milestone experiment designs here:

```text
experiments/
  MS1/
    experiment_proposal.md
  MS2/
    experiment_proposal.md
  MS200/
    experiment_proposal.md
    milestone203_experiment.py
    plan203_arelle_proof.py
  MS3/
    experiment_proposal.md
    milestone3_indicator_engine.py
  MS4/
    experiment_proposal.md
  MS5/
    experiment_proposal.md
    milestone5_retrieval_pipeline.py
  MS6/
    experiment_proposal.md
  MS7/
    experiment_proposal.md
```

Folder naming rule:

- Use `MS1`, `MS2`, `MS3`, and so on for whole-number milestones.
- Use `MS200` for Milestone 200.
- Keep runnable experiment scripts inside the same milestone folder as their
  proposal.

## Data Modes

Use these names consistently:

```text
fixture
  Uses saved sample data under data/fixtures/.
  Does not contact SEC or Gemini.
  Best for repeatable milestone inspection.

local
  Uses local project storage such as stock_data.db and data_store/filings/.
  May write generated local storage when the experiment intentionally ingests
  or refreshes a company.
  Shared isolated experiment storage should live under experiments/storage/
  when multiple milestone experiments need to inspect the same generated state.

live
  Contacts an external service such as SEC or Gemini.
  Must be explicit because data, network behavior, and credentials can change.
```

Prefer `fixture` for repeatable early inspections. Use `local` for workflows
that need to inspect the current database. Use `live` only when the experiment
is specifically about real external behavior.

## Standard Proposal Contents

Each `experiment_proposal.md` should define:

- purpose
- human question
- milestone scope
- recommended script location
- data modes
- input cases
- proposed report output
- required report sections
- implementation guidance
- artifacts to inspect
- edge cases to show
- expected outcome

The proposal should be explicit enough that a coding agent can implement the
runnable experiment without guessing what the report output should show.

## Milestone Index

| Milestone | Proposal file | Main inspection theme |
| --- | --- | --- |
| 1 | `experiments/MS1/experiment_proposal.md` | Project scaffold, settings, API health |
| 2 | `experiments/MS2/experiment_proposal.md` | SEC/XBRL ingestion, filing paths, raw facts |
| 200 / 203 | `experiments/MS200/experiment_proposal.md` | Update checks, persisted industry labels, Inline XBRL extensions, governed concept mapping, base metric lineage, the schema-free Plan 203 proof, and a read-only stage-by-stage mapping inspection report |
| 3 | `experiments/MS3/experiment_proposal.md` | Derived indicators, period-appropriate active-window yearly and quarterly tables, duration-basis checks, formulas, source metric traceability |
| 4 | `experiments/MS4/experiment_proposal.md` | Deterministic trends, comparisons, chart-ready output |
| 5 | `experiments/MS5/experiment_proposal.md` | Filing chunking and retrieval evidence |
| 6 | `experiments/MS6/experiment_proposal.md` | Gemini configuration, prompt source, call metadata |
| 7 | `experiments/MS7/experiment_proposal.md` | RAG answer separation, evidence references, unsupported claims |

## Milestone 203 Inspection Command

After configuring `SEC_USER_AGENT`, installing the exact reviewed taxonomy
packages, and choosing an existing SQLite database, run:

```powershell
uv run python experiments/MS200/milestone203_experiment.py --ticker MSFT --database stock_data.db
```

The command contacts SEC for the latest requested 10-K and 10-Q, uses the
schema-free Plan 203 Arelle proof, reads approved mappings through SQLite
query-only mode, and saves
`experiments/MS200/milestone203_mapping_report_MSFT.md`. The report presents
fact validation and selection, duplicate/quarantine accounting, the complete
applicable target bundle split into mapped and explicitly missing sections, and
deterministic Arelle-evidence inference for missing targets. Inference is shadow
evidence only: it does not write or approve a mapping, generate a formula, or
call an LLM.
If a legacy database does not yet contain `xbrl_concept_mappings`, the report
shows that absence and continues with source-controlled mappings; it never
initializes the table during inspection.

## Update Policy

Update this file when:

- milestone experiment folder naming changes
- a milestone proposal file is added, removed, or renamed
- the standard proposal contents change
- the data-mode definitions change

Update the relevant `experiments/MS*/experiment_proposal.md` when:

- an experiment command changes
- expected printed output changes
- expected outcome changes
- a milestone moves from planned to implemented
- the human question or input cases for that milestone change

Update `docs/structure.md` when:

- `docs/experiments.md` is added, removed, or renamed
- the `experiments/` folder is added
- milestone experiment folders are added, removed, or renamed
- runnable experiment files are added, removed, or renamed
- experiment responsibilities change materially
