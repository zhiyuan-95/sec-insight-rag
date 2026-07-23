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

mapping_shadow_candidates
  inspectable non-authoritative Plan 203 mapping suggestions

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
- metric coverage resolution: a metric-level review packet that combines target
  tag coverage, approved alternates, and formula/zero diagnostics so the next
  reviewer or LLM choice is about one internal metric, not each raw target tag.
- missing target XBRL concept: a target or candidate XBRL concept expected for
  the company's approved industry labels but not found after deterministic
  mapping.
- hard industry label: one of the fixed 11 industry tags assigned to a company.
- target XBRL concept set: the union of common base candidate XBRL concepts
  plus industry-specific candidate XBRL concepts for the company's approved
  hard industry labels.
- Round 1 hard mapping: direct deterministic matching from known candidate XBRL
  concept names to observed XBRL concepts.
- canonical mapping flow: candidate XBRL concept -> observed XBRL concept ->
  raw XBRL fact -> approved mapping -> system financial metric.
- metric resolution review flow: missing internal metric -> one evidence packet
  -> reviewer/LLM recommends formula from raw concepts, zero target, or no
  evidence -> approved decision before any persisted metric use.

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

## Hard Mapping And Missing Target Review

Mapping runs through deterministic hard mapping only:

1. source-controlled mappings from `src/processing/mapping_catalog.py`
2. previously approved learned mappings from `xbrl_concept_mappings`

Only those approved mappings can create direct `financial_metrics` rows. The
legacy active-window workflow does not trigger candidate mapping generation.
The additive Plan 203 annual mapping seam may generate deterministic shadow
candidates after direct mapping, but those candidates are stored only in
`mapping_shadow_candidates`; they never count as mapped coverage and cannot
populate `financial_metrics`.

For each Plan 203 fiscal period, direct mapping consumes only the
latest-valid, precedence-selected Arelle or Company Facts observation view. A
known concept-to-metric mapping is usable only when the selected observation
has a numeric value, compatible instant or duration period type, compatible
basic unit family, usable consolidated/dimensional context, and no blocking
diagnostic tied to that selected fact. A rejected direct candidate leaves its
target missing.

The period's missing-target set is calculated only after every eligible direct
mapping has run. Successfully mapped metrics are excluded. Shadow candidates
do not remove a target from this set and their scores or evidence are not part
of the interface supplied to the later LLM judge-packet builder.

The Plan 203 judge-packet builder consumes that exact missing-target set. It
creates one versioned, deterministic semantic packet containing:

1. target definitions and governed candidate concept identities
2. usable period-backed concepts, plus focused context-only concepts
3. labels, documentation, taxonomy and source-system attribution
4. precedence-selected presentation, calculation, definition and formula
   relationships, including validation-blocked relationships marked unusable
5. formula assertion status and validation evidence identifiers

Only a concept backed by a usable precedence-selected fact for the period is
marked as an executable formula component. Related concepts without such a
fact remain visible as context but cannot be selected as components. Arelle
relationship validation does not silently remove evidence from the packet:
blocked relationships remain visible with an explicit unusable marker so the
judges can assess the available accounting context.

The packet explicitly marks Arelle semantic evidence as available or
unavailable. When cached Arelle concept IDs are unavailable, the judges still
receive the target definitions and usable concept pool, but no unscoped
relationship graph is substituted.

Reported numeric values, raw fact IDs, dates, units, accessions, fiscal labels,
and shadow-inference scores are excluded from packet content and its stable
hash. Period identifiers are carried only as application membership.

Annual periods share one future recommendation request only when their company,
complete semantic packet (including exact missing targets), and set of exactly
three distinct judge models are identical. Model order is not material; a
different model, target, concept, relationship, assertion, validation, or
company creates a different group. This grouping seam does not call models,
record judge responses, create financial metrics, or change approved mappings.

Unresolved coverage should be reviewed at the internal-metric level. The metric
coverage resolver groups all target tags for one metric and presents one review
surface with:

1. existing mapped target evidence
2. approved alternate concept coverage
3. formula-from-raw-concepts diagnostics
4. zero-target diagnostics with affirmative same-period evidence
5. no-evidence cases

The LLM or reviewer may recommend one unresolved path, but only a reviewed
mapping can populate `financial_metrics`. Formula and zero-target choices are
review evidence unless a separate reviewed decision type is explicitly added.
Formula-from-raw-concepts evidence should be generated once per unresolved
metric and distinct active-window raw concept pool. If multiple 10-K or 10-Q
periods expose the same pool, the same model recommendation should be shown with
period coverage instead of triggering another provider request for each period.

The governing rule is:

```text
hard mappings populate metrics; formula/zero recommendations remain report evidence
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

Normal refreshes should load the approved company concept profile first. The
report should surface missing targets for formula/zero review when evidence says
the profile may be incomplete or stale, for example:

- the approved hard industry labels changed
- a newer 10-K causes label reclassification
- an approved concept disappears from new active periods
- a required indicator input becomes missing
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

Unknown SEC/XBRL concepts are not failures by default. They are raw evidence for
later mapping review.

Only approved learned mappings participate in the current hard-mapping flow.
Older local databases may still contain historical review rows with these
statuses, but the current missing-target process does not generate new
candidate rows:

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

- a compact summary of the run and review-only boundary
- every target metric marked as mapped or missing, with common-base versus
  industry-special classification
- proposed formula or zero rows only for missing target metrics, split into 10-K
  and 10-Q active-window sections with period context
- displayed concept values without taxonomy prefixes such as `us-gaap:` or
  `custom:`

Detailed raw-fact coverage, company labels, Inline XBRL coverage, approved
learned mappings, provider-level formula diagnostics, cache details, and
unknown concepts remain available in SQLite and CSV exports. The Markdown
report presents formula/zero evidence for later review. It does not decide
pass/fail or approve mappings.
