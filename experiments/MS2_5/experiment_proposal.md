# Milestone 2.5 Experiment Proposal: Plan 2.5 Ingestion Manual Examination

## Purpose

This experiment is the official manual examination harness for the new Plan 2.5
company ingestion workflow. It lets a human inspect what the actual
`ingest_company()` workflow creates, reuses, refreshes, and preserves for one
manually chosen company.

The experiment uses live SEC behavior and persistent isolated local storage. It
should not mutate the real project database.

The experiment presents evidence. It does not decide success, failure, or
partial success. The project owner reviews the generated report, SQLite
database, and CSV exports, then judges whether the behavior looks correct.

Plan 2.5 ingestion owns the company-level workflow between raw SEC/XBRL facts
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

For a company I choose, what does Plan 2.5 ingestion do during setup and during
later already-ingested sessions: local existence, refresh due status, SEC update
check, newly ingested filings, next check dates, and stored evidence?

## Milestone Scope

This experiment covers:

- one manually chosen ticker per run
- the actual `src.ingestion.ingest_company()` workflow
- live SEC company initialization through Plan 2.5 ingestion
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
  alternates, semantic candidates, and formula/zero diagnostics into one
  reviewer or LLM choice surface per internal metric
- alternate SEC/XBRL tags that map to the same internal business metric
- unknown SEC/XBRL concepts not currently mapped to base financial metrics
- Inline XBRL extension and dimensional fact coverage
- semantic mapping candidates that require review before use
- approved learned mappings with global, industry, or company scope
- missing exact target tags whose canonical metric is recovered through an
  approved alternate concept
- report-only LLM formula proposal diagnostics for unresolved target concepts
  after hard mapping and semantic mapping, using period-scoped raw fact pools
  that include found targets, mapped base metrics, approved alternates, and
  unknown/unmapped raw facts, with target-compatible unit filtering,
  statement-first prompting, active-period context coverage, and exact-context
  cache reuse for identical target/model/raw-concept pools
- report-only debt recovery diagnostics for missing `debt_current` and
  `debt_noncurrent`, including component statuses, assumed-zero components,
  skip reasons, formula versions, and source metric/raw fact IDs
- saved Plan 2.5 target mapping report with a compact summary, mapped/missing
  target metric status with common-base versus industry-special classification,
  semantic candidates for missing metrics split into 10-K and 10-Q active-window
  subsections, and proposed formula rows split into 10-K and 10-Q active-window
  subsections with taxonomy prefixes removed from displayed concept values

This experiment does not cover derived indicators, deterministic analytics,
retrieval indexes, Gemini calls, RAG answers, frontend behavior, durable
recovered metric storage, indicator use of recovered values, identity
inference, or pass/fail grading.

## Recommended Location

```text
experiments/MS2_5/
  experiment_proposal.md
  milestone25_live_sec_inspection.py
  prewarm_target_embeddings.py
  milestone25_mapping_report_<TICKER>.md

experiments/storage/
  experiment.db
  filings/

data/exports/
  ms2_5/
    companies.csv
    filings.csv
    raw_xbrl_facts.csv
    financial_metrics.csv
    company_industry_labels.csv
    xbrl_concept_mappings.csv
    metric_traceability_sample.csv
```

The experiment should write a compact report to
`milestone25_mapping_report_<TICKER>.md` by default and should not print the
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
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER
```

Compatibility saved report run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER --write-report
```

Detailed saved report run:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER --full-report
```

Default report run with report-only LLM formula proposals:

```text
uv run python experiments/MS2_5/milestone25_live_sec_inspection.py --ticker YOUR_TICKER
```

Use `--no-formula-proposals` to skip provider calls for a cheaper report-only
mapping run. Use `--formula-proposal-target-limit N` for a capped live-provider
smoke test.
The formula proposal panel evaluates active 10-K and 10-Q filing periods for
each missing metric. It sends each provider one request per distinct metric,
unit, period type, form, statement bucket set, and raw concept pool. When
multiple active periods expose the same pool, one model recommendation is shown
with period coverage for all matching periods. When active periods expose
different raw concept pools, the report can show different period-scoped formula
recommendations. The full eligible active-period raw fact pool remains
available in SQLite and CSV export evidence.

Rules:

- exactly one ticker is accepted per run
- the compact summary is saved to `milestone25_mapping_report_<TICKER>.md` by default
- the report body is not printed to the terminal
- while formula proposals run, the terminal prints process progress: how many
  missing targets were selected, which missing metric/statement is being
  handled, each period context, and the final context count
- after formula proposals complete, the terminal prints final recommendation
  progress: the final recommendation model, each grouped recommendation request,
  the period option contexts covered by that request, option counts by type, and
  selected/no-recommendation/unavailable/failed completion counts
- `--full-report` is accepted for compatibility; it does not add old
  target-level, provider-level, raw-fact, or unknown-concept appendices
- `--write-report` is accepted for compatibility; the report is already saved
- `prewarm_target_embeddings.py` precomputes target XBRL concept candidate
  vectors for common-base and every hard-industry bundle
- both 10-K and 10-Q behavior are presented for that ticker
- normal runs do not delete `experiments/storage/experiment.db`; repeat runs
  should make already-ingested behavior visible
- hidden support options may override the database, report, filings, and
  export paths, but normal use should rely on the stable paths above

## Report And Evidence Artifacts

Main report output:

```text
experiments/MS2_5/milestone25_mapping_report_<TICKER>.md
```

Kept SQLite artifact:

```text
experiments/storage/experiment.db
```

Supporting CSV artifacts:

```text
data/exports/ms2_5/
```

## Saved Report Shape

The saved report should be compact, intuitive, and metric-first. The reader
should see the mapping decision surface directly, without provider-level cache
diagnostics, raw-fact appendices, or unrelated lineage tables.

Sections:

0. Compact Summary
0A. XBRL Concepts Provided By Period
1. Target Metrics Mapping Status
2. Semantic Candidates For Missing Targets
3. Proposed Formulas For Formula Recommendations
4. Final Recommendations For Missing Targets

Section 0A presents the count of distinct selected XBRL concepts provided to
formula generation for each period, deduped across provider/model calls. It
uses a yearly table for 10-K and a year-by-quarter matrix for 10-Q.
Section 1 lists every target metric, marks it as mapped or missing, and labels
the metric source as common base or the actual hard-industry label name.
Section 1 is sorted by metric type and uses this column order: Metric type,
Metric, Statement, Mapping status, Mapped target concepts, Coverage detail,
Approved alternates, Target XBRL concepts checked. Section 2 lists semantic
candidates only for missing target metrics, omits the target-concept column, and
splits rows into 10-K and 10-Q active-window subsections with period coverage.
When all active periods are covered, period coverage is abbreviated as a start
and end range such as `active 10-K periods: 2021 FY - 2025 FY` or
`active 10-Q periods: 2023 Q1 - 2026 Q2`. Section 3 lists proposed formula
evidence only for missing target metrics and splits rows into 10-K and 10-Q
active-window subsections. Agreement rows should collapse when the full
provider/formula decision set is the same. When providers disagree for a period,
show separate provider rows instead of putting multiple provider formulas in the
same Formula cell. Provider-specific disagreement rows may still collapse across
periods when the same provider gives the same formula. Section 3 should not
include Target concept, Components, or recommendation columns; final choice
language belongs in Section 4. Section 3 period context should show only compact filing periods:
10-K rows use years such as `2023` or `2023-2025`, and 10-Q rows use
year-quarter labels such as `2021 q1` or `2021 q1 - 2021 q3`; omit raw suffixes
such as period type, unit, and form. 10-Q report labels should not show Q4.
If a formula is too long for the Formula column, the Formula cell should show
an annotation such as `[F1]`, and the full formula should be listed under the
table in a Formula annotations block.
Section 4 is the period-level final recommendation section, split into 10-K
and 10-Q subsections. Each row represents one missing metric for one period
group and shows the semantic candidate, proposed formula evidence, and possible
zero evidence that apply to that same period group. A separate final
recommendation LLM call chooses exactly one option from those supplied choices:
one proposed formula, the semantic candidate, `0`, or no recommendation when
the evidence is insufficient. Periods with the same metric, statement, and
identical option set should share one final recommendation call, then expand the
selected answer back to each covered period. When those recommended solutions
and the final choice are identical across periods, Section 4 should collapse
them into one row and compact the Period context like Section 3.
Formula evidence should show only formula text, without provider/model source
details. Final recommendation should show the selected recommendation value
itself: the formula text, the semantic candidate, or `0` for zero-target
recommendations. If the final model is unavailable, fails, or chooses an
invalid option, the row should show `needs_review`. When Section 3 annotated a
selected formula, Section 4 should reuse that annotation instead of reprinting
the long formula. Displayed concept values should omit taxonomy prefixes such
as `us-gaap:` or `custom:`.

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
  one metric-level review row before asking an LLM or reviewer to choose among
  semantic candidate, formula-from-raw-concepts, zero-target, or no-evidence.
- Reuse `src/ingestion/inline_xbrl.py` and Arelle for active filing extension
  taxonomy loading; keep normalization in `src/processing/inline_xbrl.py`.
- Reuse `src/processing/semantic_mapping.py` only to generate review candidates.
- Read approved learned mappings from `xbrl_concept_mappings`; never treat a
  semantic candidate as an approved base metric mapping.
- Prewarm target XBRL concept candidate vectors for the entire mapping catalog;
  embed observed company unknown concepts only when semantic discovery runs.
- Keep LLM formula proposal prompt text in `src/analyze/prompts.py`, provider
  calls in `src/analyze/xbrl_formula_proposals.py`, and period context
  construction, target-compatible unit filtering, exact-cache reuse, and deterministic validation in
  `src/processing/formula_proposals.py`. The provider panel is Gemini plus
  OpenAI `gpt-4.1-mini`. The Section 4 final recommendation step is a separate
  OpenAI call using `OPENAI_FINAL_RECOMMENDATION_MODEL`, defaulting to
  `gpt-5.5`, and it has its own exact-context cache under
  `data_store/knowledge/final_recommendations/`.
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
- Save the compact Plan 2.5 target mapping report to
  `milestone25_mapping_report_<TICKER>.md` by default without printing the
  report body to the terminal.
- Keep target-level, provider-level, raw-fact, unknown-concept, validation,
  cache, and component diagnostic tables out of the saved Markdown report.
  Source rows remain available in SQLite and CSV exports.
- Accept `--write-report` as a compatibility flag, not as a separate output
  mode.
- Store Decimal-compatible numeric text values as they come from the storage
  layer; do not convert report values through SQLite `REAL`.

## Storage To Inspect

The kept experiment database should contain the Milestone 2.5 tables:

```text
companies
filings
raw_xbrl_facts
financial_metrics
```

Generated CSV exports remain under:

```text
data/exports/ms2_5/
```

The saved report should use Markdown tables for the compact summary, target
metric mapping status, semantic candidates for missing targets, and proposed
formulas for formula recommendations.
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
