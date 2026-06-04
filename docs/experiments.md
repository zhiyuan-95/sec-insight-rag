# Experiment Runbook

## Purpose

This runbook defines the shared philosophy and location rules for milestone
experiments. The explicit design for each milestone belongs in that milestone's
own proposal file under `experiments/`.

Use this file as the central index. Use the milestone proposal files for the
actual experiment design.

## Core Rule

```text
Tests verify.
Experiments demonstrate.
Milestone proposal files define exactly what to print and inspect.
```

An experiment is a runnable, human-readable showcase of one milestone's main
functionality. It should mimic the way the project owner would naturally inspect
that stage from the terminal:

```text
I try the important user action.
I print what the system found or created.
I inspect counts, paths, dates, table names, and sample rows.
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
  MS2_5/
    experiment_proposal.md
  MS3/
    experiment_proposal.md
  MS4/
    experiment_proposal.md
  MS5/
    experiment_proposal.md
  MS6/
    experiment_proposal.md
  MS7/
    experiment_proposal.md
```

Folder naming rule:

- Use `MS1`, `MS2`, `MS3`, and so on for whole-number milestones.
- Use `MS2_5` for Milestone 2.5.
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
- proposed terminal report
- required printed sections
- implementation guidance
- artifacts to inspect
- edge cases to show
- expected outcome

The proposal should be explicit enough that a coding agent can implement the
runnable experiment without guessing what the terminal output should show.

## Milestone Index

| Milestone | Proposal file | Main inspection theme |
| --- | --- | --- |
| 1 | `experiments/MS1/experiment_proposal.md` | Project scaffold, settings, API health |
| 2 | `experiments/MS2/experiment_proposal.md` | SEC/XBRL ingestion, filing paths, raw facts |
| 2.5 | `experiments/MS2_5/experiment_proposal.md` | Existing vs new company behavior, update checks, base metrics |
| 3 | `experiments/MS3/experiment_proposal.md` | Derived indicators, formulas, source metric traceability |
| 4 | `experiments/MS4/experiment_proposal.md` | Deterministic trends, comparisons, chart-ready output |
| 5 | `experiments/MS5/experiment_proposal.md` | Filing chunking and retrieval evidence |
| 6 | `experiments/MS6/experiment_proposal.md` | Gemini configuration, prompt source, call metadata |
| 7 | `experiments/MS7/experiment_proposal.md` | RAG answer separation, evidence references, unsupported claims |

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
