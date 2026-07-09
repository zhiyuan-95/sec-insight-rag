# Mapping Policy

## Purpose

This policy defines how SEC/XBRL raw facts become curated base financial
metrics in SEC Insight RAG.

The system keeps these layers separate:

```text
raw_xbrl_facts
  broad archive of normalized SEC/XBRL reported facts

mapping catalog
  source-controlled expectations and approved raw concept mappings

financial_metrics
  curated base metrics used by indicators and analysis
```

Raw fact ingestion should remain broad. Metric mapping should remain selective.

## Mapping Vocabulary

- data lineage view: shows where a value came from, how the system translated
  it, and whether it is available for the calculation or report being inspected.
- raw XBRL fact: one reported fact from SEC/XBRL, stored in `raw_xbrl_facts`.
- XBRL concept / SEC tag: the raw tag name from SEC/XBRL, such as `Revenues`,
  `NetIncomeLoss`, or `RevenueFromContractWithCustomerExcludingAssessedTax`.
- observed XBRL concept: an XBRL concept that was actually found in a
  company's ingested filing data.
- unknown XBRL concept: an observed XBRL concept that the system does not
  currently map to a system financial metric through the source-controlled
  catalog or an approved learned mapping.
- system financial metric: the internal metric name the system understands,
  such as `revenue`, `net_income`, `inventory`, or `operating_cash_flow`.
- target XBRL concept: an SEC/XBRL tag that the system intentionally looks for
  because it may map to a system financial metric or support an indicator.
- candidate XBRL concept: one possible SEC/XBRL tag for a system financial
  metric. For example, `RevenueFromContractWithCustomerExcludingAssessedTax`,
  `Revenues`, and `SalesRevenueNet` are candidate concepts for `revenue`.
- approved mapping: a trusted mapping from an XBRL concept to a system
  financial metric. Only approved mappings can populate `financial_metrics`.
- approved company concept profile: the reusable company-specific view of
  approved XBRL concepts that map into system financial metrics for one
  company. It is built from global, industry, and company-scoped approved
  mappings after ingestion/review, and reused on later ingestions until labels
  or evidence indicate it is stale.
- missing target XBRL concept: a target or candidate XBRL concept expected for
  the company's approved industry labels but not found after deterministic
  mapping.
- hard industry label: one of the fixed 11 industry tags assigned to a company.
- target XBRL concept set: the union of common base candidate XBRL concepts
  plus industry-specific candidate XBRL concepts for the company's approved
  hard industry labels.
- direct mapping: deterministic matching from source-controlled catalog
  entries and approved learned mappings to observed XBRL concepts.
- canonical mapping flow: observed XBRL concept -> raw XBRL fact ->
  source-controlled or approved learned mapping -> system financial metric.
- learned mapping review flow: unknown XBRL concept -> human review ->
  approved or rejected learned mapping.

## Broad Raw Ingestion

The ingestion layer should continue to normalize and store broad SEC
companyfacts data. Because the SEC companyfacts API contains non-custom,
entity-wide facts, active filing Inline XBRL is conditionally parsed with
Arelle when canonical targets remain missing. This supplements the archive with
issuer-extension concepts and dimensional standard facts.

Inline XBRL facts must preserve namespace, context, dimensions, consolidation
state, source document, period, unit, and accession lineage. Dimensional facts
remain raw-only unless an explicitly reviewed segment mapping allows them.

Industry labels and target concept bundles must not be used as ingestion
filters. They are used after ingestion to explain what the system expected,
what it found, what mapped into `financial_metrics`, and what remains raw-only
evidence.

## Hard Industry Labels

The fixed hard industry label set is:

```text
Energy
Materials
Industrials
Consumer Discretionary
Consumer Staples
Health Care
Financials
Information Technology
Communication Services
Utilities
Real Estate
```

A company can have one or more labels from this set. There are no secondary
labels. If a company operates in multiple industries, assign multiple labels.

## Company Label Assignment

The source-controlled company label registry in
`src/processing/company_industry_labels.py` remains the initial reviewed source.
Assigned labels and their evidence are persisted in
`company_industry_labels` so future processing can reuse them.

Each assignment should show:

- ticker
- CIK
- assigned hard industry labels
- assignment source
- assignment reason
- supporting evidence
- review date
- label status
- notes

SIC code, SIC description, business descriptions, and observed XBRL concept
patterns are supporting evidence. They are not the source of truth in the first
implementation.

Do not silently infer a company label from observed raw XBRL concepts. That
creates circular logic:

```text
observed raw facts
  -> inferred industry label
  -> expected raw facts
```

If no source-controlled or high-confidence Gemini assignment exists, the report
should not claim complete industry-specific target coverage. Gemini may assign
labels from the latest 10-K Item 1 Business section when configured, but only
when the returned labels are supported and meet the configured confidence
threshold. Low-confidence or invalid Gemini labels are ignored rather than sent
to a human approval queue. Kept Gemini labels must retain their evidence,
confidence, source accession, prompt version, and classifier version. SIC and
observed XBRL concept patterns remain supporting evidence, not label authority.

## Target Raw Fact Catalog

The mapping catalog lives in `src/processing/mapping_catalog.py`.

The catalog defines:

- common base target facts used for most companies
- extra hard-industry target facts beyond the common base concepts
- approved raw concept to internal metric candidates
- target metadata such as statement type, core vs specialized need, priority,
  and consolidated vs segment meaning

Industry bundles should contain only extra industry-specific concepts. Do not
duplicate common base concepts inside industry bundles. If a common base concept
is especially important for an industry, record that later as metadata rather
than duplicating the raw concept.

Common targets plus every assigned industry bundle form a union. Duplicate raw
aliases are collapsed by canonical metric, taxonomy, concept, and statement
type; they are not stored as duplicate target definitions or duplicate internal
metrics. This union combines target expectations only. It must never add or
merge numeric fact values across industry labels.

## Mapping Rules

Different SEC/XBRL concepts can map to the same internal metric. For example:

```text
RevenueFromContractWithCustomerExcludingAssessedTax -> revenue
Revenues -> revenue
SalesRevenueNet -> revenue
```

Internal metric names should remain stable. Indicator formulas should calculate
from internal metric names, not raw XBRL concept names.

`NetIncomeLoss -> net_income` is intentional. The internal `net_income` metric
represents bottom-line income or loss for the period. Positive values mean net
income/profit, and negative values mean net loss.

Do not create new internal metrics only to reduce the unknown concept count.
Only add a mapping when the raw concept has a reviewed business meaning in the
system.

## Direct And Learned Mapping

Mapping runs through deterministic inputs only:

1. Source-controlled catalog mappings in `src/processing/mapping_catalog.py`.
2. Previously approved learned mappings in `xbrl_concept_mappings`.

The ingestion workflow does not generate model-similarity mapping candidates, does
not write automated `candidate` mapping rows, and does not use model confidence
to approve mappings.

If target metrics remain missing after direct mapping, they remain missing for
`financial_metrics`. The MS2.5 report can optionally ask LLM providers for
report-only formula or zero-target diagnostics using same-period raw facts.
Those diagnostics do not approve mappings, do not insert recovered metrics, and
do not feed indicators.

When a human later approves a learned mapping, that mapping may use global,
industry, or company scope. Future ingestion runs load it as deterministic
mapping state and may populate `financial_metrics` when the same observed XBRL
concept appears again.

The governing rule is:

```text
catalog and approved mappings populate metrics; diagnostics only inform review
```

## Approved Company Concept Profile

After a company has approved labels and approved mappings, the system should
treat the applicable approved mappings as that company's reusable concept
profile.

```text
approved company concept profile =
  global approved mappings
  + industry approved mappings for the company's approved hard labels
  + company approved mappings for the company's CIK
```

The profile is mapping state, not an ingestion filter. Raw ingestion remains
broad on every run. The profile only controls which observed raw facts are
allowed to populate `financial_metrics`.

Normal refreshes should load the approved company concept profile first and
reuse it whenever the same observed concepts appear in new raw facts. Review
the profile when evidence says it may be incomplete or stale, for example:

- the approved hard industry labels changed
- a newer 10-K causes label reclassification
- an approved concept disappears from new active periods
- a required indicator input becomes missing
- a new issuer-extension concept appears for a missing target metric
- a reviewer rejects or invalidates an existing mapping

This keeps later ingestion fast while preserving mapping quality and traceability.

## Mapping Statuses

Reports should use status labels to explain what happened:

```text
found_mapped
found_unmapped
missing_target
needs_review
skipped_quality
segment_only
not_applicable
```

Unknown SEC/XBRL concepts are not failures by default. They are raw evidence and
review inputs.

Learned mapping workflow statuses are separate. Automated ingestion only uses
`approved`; `candidate` and `rejected` are for explicit review history when
present:

```text
candidate
approved
rejected
```

## Segment And Consolidated Facts

Company-level indicators should use consolidated company-level facts.

Segment-level facts should remain separate unless an indicator formula
explicitly says it is segment-level. The mapping catalog should preserve the
`consolidated_or_segment` distinction so segment facts do not silently enter
company-level metrics.

## Experiment Reporting

The MS2.5 report should show:

- source-controlled company industry labels
- assignment source, reason, supporting evidence, and status
- raw fact mapping coverage
- target raw fact coverage
- target facts found in `raw_xbrl_facts`
- target facts missing from `raw_xbrl_facts`
- target facts found but not mapped into `financial_metrics`
- unknown SEC/XBRL concepts that remain raw-only evidence
- Inline XBRL extension and dimensional fact coverage
- approved learned mappings and their scope
- exact target tags that are absent but whose canonical metric is recovered by
  an approved alternate concept
- report-only formula or zero-target decisions for missing targets when the
  enabled LLM panel finds supporting same-period raw-fact evidence

The report presents evidence. It does not decide pass/fail.
