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
  currently map to a system financial metric and does not currently treat as a
  target XBRL concept.
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
- semantic mapping candidate: a possible mapping suggested by vector
  similarity. It requires review and must not populate `financial_metrics`
  automatically.
- missing target XBRL concept: a target or candidate XBRL concept expected for
  the company's approved industry labels but not found after deterministic
  mapping.
- hard industry label: one of the fixed 11 industry tags assigned to a company.
- target XBRL concept set: the union of common base candidate XBRL concepts
  plus industry-specific candidate XBRL concepts for the company's approved
  hard industry labels.
- Round 1 hard mapping: direct deterministic matching from known candidate XBRL
  concept names to observed XBRL concepts.
- Round 2 semantic mapping: vector comparison between missing target XBRL
  concept vectors and unknown company XBRL concept vectors.
- canonical mapping flow: candidate XBRL concept -> observed XBRL concept ->
  raw XBRL fact -> approved mapping -> system financial metric.
- semantic review flow: unknown XBRL concept -> semantic mapping candidate ->
  reviewed approved mapping.

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
type; they are not stored as duplicate vectors or duplicate internal metrics.
This union combines target expectations only. It must never add or merge
numeric fact values across industry labels.

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

## Adaptive Mapping

Mapping runs in two rounds:

1. Deterministic mappings from the source-controlled catalog and previously
   approved learned mappings.
2. Semantic candidate generation for canonical metrics still missing after the
   deterministic round.

Semantic similarity is a discovery mechanism, not mapping authority. Candidate
generation compares canonical target definitions and approved aliases with
observed concept names, labels, and documentation. It also requires compatible
period type and considers only numeric, consolidated facts for company-level
metrics.

Target XBRL concept candidate vectors should be prewarmed for every common-base
and hard-industry catalog candidate. Observed company concepts are embedded only
when semantic discovery runs, because they depend on the actual ingested raw
facts for that company.

Candidates are stored in `xbrl_concept_mappings` with status `candidate`,
confidence, method, scope, and evidence. They do not create
`financial_metrics` rows. A reviewer must mark a candidate `approved` or
`rejected`. Approved mappings may use global, industry, or company scope and
become deterministic inputs on later ingestion runs.

The governing rule is:

```text
embeddings suggest; reviewed mappings approve
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
skip semantic discovery when the profile still covers the required target
metrics. Semantic discovery should run again only when evidence says the profile
may be incomplete or stale, for example:

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
review candidates.

Learned mapping workflow statuses are separate:

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
- semantic mapping candidates awaiting review
- approved learned mappings and their scope
- exact target tags that are absent but whose canonical metric is recovered by
  an approved alternate concept
- report-only formula or zero-target decisions for missing targets when the
  enabled LLM panel finds supporting same-period raw-fact evidence

The report presents evidence. It does not decide pass/fail.
