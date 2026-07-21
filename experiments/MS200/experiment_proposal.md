# Milestone 200 Experiment Proposal: Plan 200 Ingestion Manual Examination

## Purpose

This experiment is the official manual examination harness for the new Plan 200
company ingestion workflow. It lets a human inspect what the actual
`ingest_company()` workflow creates, reuses, refreshes, and preserves for one
manually chosen company.

The experiment uses live SEC behavior and persistent isolated local storage. It
should not mutate the real project database.

The experiment presents evidence. It does not decide success, failure, or
partial success. The project owner reviews the generated report, SQLite
database, and CSV exports, then judges whether the behavior looks correct.

Plan 200 ingestion owns the company-level workflow between raw SEC/XBRL facts
and future derived indicators:

```text
company request
  -> local company registry and refresh-state check
    -> live SEC initialization or refresh when needed
      -> full raw_xbrl_facts archive
        -> active 10-K/10-Q filing evidence
          -> active-window financial_metrics
            -> data lineage view for financial_metrics availability
```

The experiment should show whether a chosen ticker can be initialized through
the real ingestion workflow, then preserved in steady experiment storage so
later runs can inspect already-ingested behavior, local refresh decisions, SEC
check behavior, newly ingested filings, and next check dates.

## Human Question

For a company I choose, what does Plan 200 ingestion do during setup and during
later already-ingested sessions: local existence, refresh due status, SEC update
check, newly ingested filings, next check dates, and stored evidence?

## Milestone Scope

This experiment covers:

- one manually chosen ticker per run
- the actual `src.ingestion.ingest_company()` workflow
- live SEC company initialization through Plan 200 ingestion
- persistent isolated experiment storage
- first-time setup ingestion when the ticker is absent from experiment storage
- already-ingested inspection when the ticker is present from a prior run
- already-ingested session inspection after the current setup or reuse step
- company registry state
- filing inventory state
- normalized SEC companyfacts plus conditionally extracted Inline XBRL extension
  and dimensional facts in `raw_xbrl_facts`
- latest ingested 10-K and 10-Q filing dates
- next-check dates for 10-K and 10-Q refresh checks
- active analysis window state
- active filing evidence for the latest 5 fiscal years of 10-K data and latest
  12 quarters of 10-Q data
- base financial metric mapping
- metric-level data lineage summary for `financial_metrics`
- traceability from `financial_metrics` to `raw_xbrl_facts` and filings
- raw fact mapping coverage: raw facts downloaded/stored, mapped raw facts,
  unmapped raw facts, unknown raw concepts, and supported mapping catalog size
- persisted hard industry label assignment, including assignment source, reason,
  supporting evidence, classifier version, confidence, and label status
- target raw fact coverage for the assigned hard industry labels, including
  found, missing, and found-but-unmapped target facts
- metric-first coverage resolution that groups target tags, approved
  alternates, and formula/zero diagnostics into one
  reviewer or LLM choice surface per internal metric
- alternate SEC/XBRL tags that map to the same internal business metric
- unknown SEC/XBRL concepts not currently mapped to base financial metrics
- Inline XBRL extension and dimensional fact coverage
- approved learned mappings with global, industry, or company scope
- missing exact target tags whose canonical metric is recovered through an
  approved alternate concept
- report-only LLM formula proposal diagnostics for unresolved target concepts
  after hard mapping, using period-scoped raw fact pools
  that include found targets, mapped base metrics, approved alternates, and
  unknown/unmapped raw facts, with target-compatible unit filtering,
  statement-first prompting, active-period context coverage, exact-context
  cache reuse for identical target/model/raw-concept pools, and statement-scoped
  batch provider calls for uncached missing targets with compatible raw-concept
  contexts; deterministic validation uses actual fact dates inside comparative
  filings, prefers undimensioned facts when dimensional variants coexist, and
  rejects truly ambiguous same-date duplicates
- report-only debt recovery diagnostics for missing `debt_current` and
  `debt_noncurrent`, including component statuses, assumed-zero components,
  skip reasons, formula versions, and source metric/raw fact IDs
- saved Plan 200 target mapping report with a compact summary, mapped/missing
  target metric status with common-base versus industry-special classification,
  and proposed formula rows split into 10-K and 10-Q active-window subsections
  with taxonomy prefixes removed from displayed concept values and explicit
  period coverage for each provider on a grouped formula row

This experiment does not cover derived indicators, deterministic analytics,
retrieval indexes, Gemini calls, RAG answers, frontend behavior, durable
recovered metric storage, indicator use of recovered values, identity
inference, or pass/fail grading.

## Recommended Location

```text
experiments/MS200/
  experiment_proposal.md
  milestone200_live_sec_inspection.py
  milestone200_mapping_report_<TICKER>.md

experiments/storage/
  experiment.db
  filings/

data/exports/
  ms200/
    companies.csv
    filings.csv
    raw_xbrl_facts.csv
    financial_metrics.csv
    company_industry_labels.csv
    xbrl_concept_mappings.csv
    metric_traceability_sample.csv
```

The experiment should write a compact report to
`milestone200_mapping_report_<TICKER>.md` by default and should not print the
report body to the terminal.
`experiments/storage/experiment.db` should persist across runs and across
milestone experiments. The CSV exports should overwrite stable paths on each
run.
The default saved report should show the compact metric-first decision path.
`--full-report` is kept as a CLI compatibility flag, but the saved report keeps
the same decision-focused section shape instead of appending diagnostic
appendices.
`--write-report` is accepted only as a compatibility flag because the report is
now always saved.

## Data Mode

This experiment uses live SEC behavior and persistent isolated local storage.

```text
live
  Contacts SEC for the chosen ticker.
  Requires SEC_USER_AGENT.
  May observe different SEC data depending on the run date.

isolated local storage
  Writes to experiments/storage/experiment.db.
  Writes filing downloads to experiments/storage/filings/.
  Does not write to the real stock_data.db.
  Does not write filing downloads to the real data_store/filings/ path.
  Keeps the experiment database after and between runs for manual SQLite
  inspection.
```

The experiment should not use the real project database as its write target.
That keeps first-time ingestion, repeat-run reuse, refresh-date generation,
active-window selection, and filing evidence storage inspectable without
changing real local company state.

## Command

Default run:

```text
uv run python experiments/MS200/milestone200_live_sec_inspection.py --ticker YOUR_TICKER
```

Compatibility saved report run:

```text
uv run python experiments/MS200/milestone200_live_sec_inspection.py --ticker YOUR_TICKER --write-report
```

Detailed saved report run:

```text
uv run python experiments/MS200/milestone200_live_sec_inspection.py --ticker YOUR_TICKER --full-report
```

Default report run with report-only LLM formula proposals:

```text
uv run python experiments/MS200/milestone200_live_sec_inspection.py --ticker YOUR_TICKER
```

Use `--no-formula-proposals` to skip provider calls for a cheaper report-only
mapping run. Use `--formula-proposal-target-limit N` for a capped live-provider
smoke test.
The formula proposal panel evaluates active 10-K and 10-Q filing periods for
each missing metric. It loads exact per-target cache entries first, then sends
each provider one request per statement-scoped batch context for uncached
targets. A batch request may include multiple missing metrics only when they
share the same statement group, primary monetary unit, period type, form,
statement bucket set, and raw concept pool; different statement groups are sent
separately. For monetary targets, secondary monetary currencies in the same
filing period are suppressed from provider contexts instead of becoming separate
LLM requests or being mixed into the primary unit pool. When multiple active
periods expose the same pool, one model recommendation is shown with period
coverage for all matching periods. When active periods expose different raw
concept pools, the report can show different period-scoped formula
recommendations. The full eligible active-period raw fact pool, including
secondary currency facts, remains available in SQLite and CSV export evidence.

Rules:

- exactly one ticker is accepted per run
- the compact summary is saved to `milestone200_mapping_report_<TICKER>.md` by default
- the report body is not printed to the terminal
- while formula proposals run, the terminal prints process progress: how many
  missing targets were selected, which missing metric/statement is being
  handled, total model outcomes and provider-context slots, each provider's
  reused and live workload, each numbered live batch request, and the final
  context count
- `--full-report` is accepted for compatibility; it does not add old
  target-level, provider-level, raw-fact, or unknown-concept appendices
- `--write-report` is accepted for compatibility; the report is already saved
- both 10-K and 10-Q behavior are presented for that ticker
- normal runs do not delete `experiments/storage/experiment.db`; repeat runs
  should make already-ingested behavior visible
- hidden support options may override the database, report, filings, and
  export paths, but normal use should rely on the stable paths above

## Report And Evidence Artifacts

Main report output:

```text
experiments/MS200/milestone200_mapping_report_<TICKER>.md
```

Kept SQLite artifact:

```text
experiments/storage/experiment.db
```

Supporting CSV artifacts:

```text
data/exports/ms200/
```

## Saved Report Shape

The saved report should be compact, intuitive, and metric-first. The reader
should see the mapping decision surface directly, without provider-level cache
diagnostics, raw-fact appendices, or unrelated lineage tables.

Sections:

0. Compact Summary
0A. XBRL Concepts Provided By Period
1. Target Metrics Mapping Status
2. Proposed Formulas For Formula Recommendations
3. Summary Recommendation

Section 0A presents the count of distinct selected XBRL concepts provided to
formula generation for each period, deduped across provider/model calls. It
uses a yearly table for 10-K and a year-by-quarter matrix for 10-Q.
Section 1 lists every target metric, marks it as mapped or missing, and labels
the metric source as common base or the actual hard-industry label name.
Section 1 is sorted by metric type and uses this column order: Metric type,
Metric, Statement, Mapping status, Mapped target concepts, Coverage detail,
Approved alternates, Target XBRL concepts checked. Section 2 lists proposed
formula evidence only for missing target metrics and splits rows into 10-K and
10-Q active-window subsections. Section 2 should group rows by missing metric,
statement, and displayed formula so identical recommended formulas can collapse
across periods and provider/model results even when the providers cite different
component or zero-evidence details. The `LLM result count` column should count
distinct target/context/model formula results supporting the displayed formula,
not display-period labels expanded from one result. When a target/context/model
returns `no_formula`, `provider_unavailable`, or `provider_failed`, Section 2
should show a compact provider outcome row for that period context so missing
recommendation coverage is visible. Section 2 should not include
Target concept, Components, or recommendation columns. Section 2
period context should show only compact filing periods:
10-K rows use years such as `2023` or `2023-2025`, and 10-Q rows use
year-quarter labels such as `2021 q1` or `2021 q1 - 2021 q3`; omit raw suffixes
such as period type, unit, and form. 10-Q report labels should not show Q4.
If a formula is too long for the Formula column, the Formula cell should show
an annotation such as `[F1]`, and the full formula should be listed under the
table in a Formula annotations block.
Displayed concept values should omit taxonomy prefixes such as `us-gaap:` or
`custom:`.

Section 3 should contain one row for every selected missing target-period. It
should reduce the three validated model outcomes to `formula` when at least two
models return the same validated component signature, `zero` when at least two
models return validated zero evidence, and `review_required` otherwise. It
should show Form, Metric, Statement, Period context, Recommendation,
Formula / value, Validated votes, Agreeing models, and Review reason. Targets
without an eligible context, disabled formula runs, and empty eligible fact
pools should remain visible as `review_required` rows instead of disappearing.

The compact summary should include setup ingestion duration and unchanged-company
reuse duration as evidence for the local MVP performance expectations. It should
not add automatic pass/fail labels.

The report should use reader-facing status labels:

```text
mapped
covered_by_approved_alternate
needs_review
no_evidence
```

The internal resolver may still use `needs_llm_resolution`, but the report
should say `needs_review` so the LLM does not sound like the final approver.

## Implementation Guidance

- Reuse `src/ingestion/company.py` for company ingestion orchestration.
- Reuse `src/ingestion/refresh_policy.py` for update-check date logic.
- Reuse `src/processing/active_window.py` for active-window selection.
- Reuse `src/processing/base_metrics.py` for base metric mapping.
- Reuse `src/processing/company_industry_labels.py` for explicit hard industry
  label assignments. Do not infer labels silently from observed raw facts.
- Reuse `src/processing/mapping_catalog.py` for approved mapping candidates and
  target raw fact coverage.
- Reuse `src/processing/metric_coverage.py` to collapse tag-level evidence into
  one metric-level review row before asking an LLM or reviewer to evaluate
  formula-from-raw-concepts, zero-target, or no-evidence.
- Reuse `src/ingestion/inline_xbrl.py` and Arelle for active filing extension
  taxonomy loading; keep normalization in `src/processing/inline_xbrl.py`.
- Read approved learned mappings from `xbrl_concept_mappings`; only approved
  mappings can participate in hard mapping.
- Keep LLM formula proposal prompt text in `src/analyze/prompts.py`, provider
  calls in `src/analyze/xbrl_formula_proposals.py`, and period context
  construction, target-compatible unit filtering, statement-scoped batch
  grouping, exact-cache reuse, and deterministic validation in
  `src/processing/formula_proposals.py`. The ordered provider panel is OpenAI
  `gpt-5-mini`, Anthropic `claude-sonnet-5`, and Gemini
  `gemini-2.5-flash`. The Anthropic slot uses the first nonblank
  `claude-api-key`, `ANTHROPIC_API_KEY`, or `CLAUDE_API_KEY` setting; the
  Gemini slot continues to use `GEMINI_API_KEY`.
- Treat LLM formula proposals as report-only evidence. Do not approve mappings,
  persist recovered values, or feed indicators from model confidence or model
  agreement. A model may also return a report-only zero-target decision when
  same-period raw facts provide affirmative evidence that the missing target
  may be zero; that decision is still review evidence and does not create a
  financial metric.
- Reuse `src/processing/metric_recovery.py` for report-only debt recovery
  diagnostics. Do not duplicate formula logic in this experiment script.
- Reuse repositories in `src/storage/` for all database reads and writes.
- Do not calculate derived indicators inside the experiment script.
- Do not persist recovered debt values or insert them into `financial_metrics`.
- Do not let indicator formulas consume recovered debt values in this
  experiment.
- Do not duplicate SEC HTTP logic inside the experiment script.
- Do not define pass/fail labels inside the experiment script.
- Do not write to `stock_data.db`.
- Do not delete or reset `experiments/storage/experiment.db` at startup.
- Do not print secrets or the actual `SEC_USER_AGENT` value.
- Keep the default saved report compact, metric-first, and limited to the
  requested mapping evidence tables.
- Save the compact Plan 200 target mapping report to
  `milestone200_mapping_report_<TICKER>.md` by default without printing the
  report body to the terminal.
- Keep target-level, raw-fact, unknown-concept, validation, cache, and component
  diagnostic tables out of the saved Markdown report. Keep full provider-level
  diagnostics out too, except for the compact Section 2 provider outcome rows
  that expose `no_formula`, `provider_unavailable`, or `provider_failed`
  recommendation coverage gaps. Source rows remain available in SQLite and CSV
  exports.
- Accept `--write-report` as a compatibility flag, not as a separate output
  mode.
- Store Decimal-compatible numeric text values as they come from the storage
  layer; do not convert report values through SQLite `REAL`.

## Storage To Inspect

The kept experiment database should contain the Milestone 200 tables:

```text
companies
filings
raw_xbrl_facts
financial_metrics
```

Generated CSV exports remain under:

```text
data/exports/ms200/
```

The saved report should use Markdown tables for the compact summary, target
metric mapping status, and proposed formulas for formula recommendations.
Table cells should be padded to the column width so headers and values align in
the text report.
Numeric report values should use presentation-only abbreviations where useful:
`K`, `M`, `B`, and `T` represent thousands, millions, billions, and trillions.
Abbreviated values should use two decimal places when possible, and decimal
values below `1K` should be rounded to two decimal places. Stored SQLite values
and CSV exports should remain unmodified.
When multiple distinct values remain for one metric-period cell, the report
should keep them visible in the cell instead of silently dropping them.
Detailed target raw fact coverage, provider-level formula diagnostics, formula
component evidence, raw fact mapping coverage, persisted hard industry labels,
Inline XBRL extension coverage, approved learned mappings, observed alternate
tags, and unknown concepts should remain inspectable through SQLite and CSV
exports rather than appended to the saved Markdown report.

## Edge Cases To Present

The experiment should present these conditions when they occur naturally:

- SEC is unavailable or returns a retryable error
- `SEC_USER_AGENT` is missing
- ticker cannot be resolved to a CIK
- no recent 10-K is available
- no recent 10-Q is available
- update-check date cannot be generated because latest filing date is missing
- base metrics are unavailable because concepts are missing or quality-flagged
- a company does not yet have a source-controlled hard industry label assignment
- a mapped raw concept has no usable `financial_metrics` rows for the active
  window
- source raw fact ID is missing from a metric row
- duplicate or ambiguous facts are visible in raw fact quality flags

## Presentation Outcome

At the end of the experiment, the project owner should have enough evidence to
inspect:

- which ticker was used
- whether first-time setup created local state or a repeat run reused it
- whether the company exists in local storage for an already-ingested session
- whether 10-K or 10-Q refresh checks are due
- whether SEC was contacted for update checking
- whether newer filing data was ingested during the session
- what 10-K and 10-Q refresh dates were generated
- which filing accessions are stored locally
- how many rows exist in each relevant table
- which rows are inside the active analysis window
- which base metrics were mapped
- how raw XBRL concepts map into available `financial_metrics`
- which hard industry labels are assigned and why
- which target raw facts were expected, found, missing, or found but unmapped
- which base metrics can be traced back to raw XBRL facts
- where to inspect target-level, provider-level, raw-fact, and unknown-concept
  evidence
- where to open the full SQLite database and CSV exports

The experiment should stop at presentation. The human reviewer decides whether
the observed behavior is acceptable.

## Plan 203 Increment 1 Companion Proof

`plan203_arelle_proof.py` is a separate schema-free extraction and
reconciliation proof. It does not replace the Milestone 200 inspection command,
write SQLite data, activate inferred mappings, or call formula providers.

After setting `SEC_USER_AGENT` and explicitly installing the reviewed taxonomy
archives, run:

```powershell
uv run python experiments/MS200/plan203_arelle_proof.py --ticker MSFT
```

Use `--sync-taxonomies` only when the exact source-controlled registry artifacts
need to be installed. The proof selects the latest 10-K and 10-Q, builds or
verifies accession packages, proves offline Arelle loading, launches one bounded
worker per accession, and saves:

```text
experiments/MS200/experiment_report_plan203_arelle.md
```

The report exposes package identity, extraction counts, payload bytes, timings,
diagnostics, canonical eligibility, and same-accession consolidated Company
Facts reconciliation. A `degraded` or `failed` filing remains evidence only and
cannot populate metrics.

## Milestone 203 Workflow Inspection Report

`milestone203_experiment.py` is the presentation layer for the implemented
Plan 203 proof. It calls `run_plan203_proof(...)` once, then projects the
detached Arelle evidence through the existing fact-precedence and hard-mapping
APIs. It does not replace production ingestion, change a schema, persist facts
or metrics, activate an inferred mapping, generate a formula, or call an LLM.

Run the latest 10-K and 10-Q inspection with an existing mapping database:

```powershell
uv run python experiments/MS200/milestone203_experiment.py --ticker MSFT --database experiments/storage/experiment.db
```

The default artifact is:

```text
experiments/MS200/milestone203_mapping_report_MSFT.md
```

The report must show:

- a workflow table from SEC acquisition through atomic report publication
- per-accession Arelle completeness, reason when incomplete, fact/concept
  counts, selected and quarantined observations, duplicate groups, eligibility,
  and timings
- count integrity using grouped observations' raw occurrence counts
- the source-controlled Common Base bundle plus the industry bundles selected
  by approved Gemini-generated company labels stored during ingestion
- every applicable target exactly once, split into mapped and explicitly
  missing sections
- the existing hard-mapping source, including applicable approved SQLite rows
  read through query-only mode
- a visible Common Base-only fallback when approved Gemini company labels are
  unavailable; the experiment must not use the manual ticker/CIK registry
- a visible source-controlled concept-mapping fallback when a legacy read-only
  database does not contain the approved-mapping table; the experiment must not
  create it
- equal-specificity approved-mapping disagreements as excluded conflicts
- report-only deterministic Arelle-evidence inference for missing targets,
  including five 0-2 ranking categories, target-to-concept and
  concept-to-target margins, hard gates, bounded rejection examples, and
  evidence citations
- worked mapped and missing traces plus the no-write/no-LLM boundary

Namespace is not a normal mapping selector. It remains visible for lineage and
is used to abstain when the same local selector crosses unrelated taxonomy or
issuer families. Inference scores are uncalibrated within-session ranking
evidence, not probability, confidence, or human approval.

Exit code `0` means every requested form produced a complete Arelle result,
`3` means at least one requested form was incomplete while another remained
inspectable, `1` means the report had no eligible form or hit a global/report
failure, and argparse retains exit code `2` for invalid arguments.
