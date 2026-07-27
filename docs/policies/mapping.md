# Mapping Policy

## Role

This policy defines the durable rules for converting MS2 annual XBRL evidence
into system base metrics. [MS3](../milestones/MS3-base-metric-mapping.md) owns
the implementable workflow and acceptance contract.
[System Structure](../structure.md) describes the currently implemented subset.

The policy keeps these layers distinct:

```text
raw source observations
  -> precedence-selected evidence
  -> approved direct mapping or validated recovery application
  -> financial_metrics
  -> deterministic indicators
```

Raw ingestion remains broad. Mapping remains selective and traceable.

## Vocabulary

- **raw observation**: one source-attributed Arelle or SEC Company Facts
  observation before mapping.
- **XBRL concept**: a filing taxonomy concept such as `Revenues`,
  `NetIncomeLoss`, or an issuer extension.
- **system metric**: a stable internal name such as `revenue`, `net_income`, or
  `operating_cash_flow`.
- **target metric**: a system metric expected for a fiscal period from the
  common catalog and its approved industry bundles.
- **approved direct mapping**: a source-controlled or human-approved
  concept-to-system-metric rule.
- **shadow candidate**: an inspectable deterministic suggestion that is not
  approved and cannot affect current metrics or LLM judgment.
- **missing target**: a target metric that remains unavailable after every
  eligible approved direct mapping runs.
- **semantic packet**: the nonnumeric target, concept, label, documentation,
  statement, relationship, and validation evidence sent identically to each
  judge.
- **recommendation group**: one shared three-judge semantic decision for
  periods with the same company, exact missing targets, usable semantic
  evidence, and judge lineup.
- **recovery application**: deterministic selection and calculation of one
  unanimous recommendation for one fiscal period.

## Evidence Boundary

MS2 supplies mapping with:

- every selected Inline XBRL `10-K` and `10-K/A`
- Arelle-extracted concepts, labels, documentation, presentation,
  calculation, definition, and formula relationships
- Arelle XBRL and SEC validation results
- supplemental SEC Company Facts observations
- source identity, accession, fiscal period, statement, context, dimensions,
  units, and validation lineage
- latest-valid precedence for overlapping or amended observations
- the fiscal-period industry-label snapshot

Company Facts observations remain eligible even when Arelle did not extract the
same fact. Arelle is the canonical source of structure and validation, not a
filter that silently removes other raw evidence.

If multiple observations still compete for the same fact identity, use the
latest valid accession update. Preserve every original observation and the
precedence decision; never overwrite raw evidence.

Mapping must not trigger filing acquisition, Arelle execution, or source
reconciliation. It consumes the completed MS2 evidence snapshot.

## Fiscal-Period Industry Labels

The fixed industry label set is:

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

A company may receive one or more labels. Labels are fiscal-period historical
records, not one mutable company-wide value. The existing assignment mechanism
is retained with `gemini-3.1-flash-lite` as its model.

Use the latest selected original `10-K` available for that fiscal period's
assignment. A later amendment may update facts but does not reclassify the
period. Preserve the assignment source, accession, model, prompt/version
metadata, supporting evidence, confidence, and timestamp.

If the classifier cannot assign any approved label, map only common-base target
metrics for that period. Do not infer an industry from raw concept presence.

## Target Catalog

The catalog defines:

- common-base system metrics
- additional metrics for each approved industry label
- approved raw-concept candidates
- statement type, period type, priority, and consolidated/segment meaning

For one fiscal period:

```text
target metrics =
  common-base targets
  union each assigned industry's additional targets
```

Collapse duplicates by system metric and governed concept identity. The union
combines expectations only; it never merges numeric values.

Internal metric names must remain stable. Indicator formulas use internal
metric names, not raw concept names. Do not create a metric merely to reduce
the unknown-concept count.

## Direct Mapping

Direct mapping always runs before recovery:

1. source-controlled approved mappings
2. human-approved company, industry, or global mappings

A direct mapping may create a current metric only when its precedence-selected
observation is numeric and minimally compatible with the target's statement,
instant/duration basis, consolidated context, and basic unit family. A blocking
diagnostic tied to that fact makes the candidate unusable.

The latest selected accession and its statement concept pool receive
precedence. Successful direct mappings:

- populate `financial_metrics` with reported-mapping provenance
- are excluded from the missing-target set
- are never sent to the judges for recommendation or recovery

Their underlying concepts may still be components for a different missing
target.

Deterministic inferred candidates remain shadow-only. They cannot populate
`financial_metrics`, remove a missing target, rank or filter the judge packet,
or become approved without a separate review decision.

## Exact Missing Targets

Calculate missing targets independently for each fiscal period only after all
eligible direct mappings finish.

The recovery system receives system metrics, not a list of every absent raw
alias. A target is missing when no approved direct mapping produced a usable
metric for that period. Unknown raw concepts are evidence, not failures.

## Semantic Judge Packet

Build one deterministic, versioned packet from the exact missing-target set.
Include:

- target identifiers, definitions, and governed candidate concepts
- every usable concept from the relevant precedence-selected statement pools
- focused related concepts that supply accounting context
- concept labels, documentation, taxonomy/source attribution, and statement
  relationships
- Arelle presentation, calculation, definition, and formula relationships
- formula assertion and validation evidence
- explicit usable, blocked, or unavailable evidence markers

Do not remove blocked relationships silently. Show them as cautionary context,
but do not let them make a concept eligible as a formula component.

Only a concept backed by a usable fact in every covered application period may
be an executable component. Context-only concepts remain visible but cannot be
selected.

Exclude numeric values, raw fact IDs, accessions, dates, units, fiscal labels,
and shadow scores from the semantic packet. The judges decide from semantic and
accounting evidence; deterministic code selects facts and calculates values
later.

## Three-Judge Decision

Send the identical packet concurrently and independently to:

- `gpt-5-mini`
- `gemini-3.1-flash-lite`
- `gemini-2.5-flash`

The judges are blind to one another. For each exact missing target, each returns
one structured decision:

- `formula`: an addition/subtraction expression over eligible concepts
- `zero`: affirmative accounting evidence that the target is zero
- `no_formula`: insufficient semantic evidence

Recovery formulas may use `+` and `-` only. Multiplication, division, ratios,
percentages, arbitrary constants, and invented concepts are not allowed.

A decision passes automatically only when all three judges return the same
canonical decision, concepts, operators, and required evidence references.
Rationale wording and harmless commutative component ordering do not create
disagreement.

- unanimous `formula` or `zero`: eligible for deterministic application
- unanimous `no_formula`: explicit abstention
- any semantic disagreement: `needs_review`
- missing, malformed, or failed response: `technical_failure`

Neither a majority nor one strong model is sufficient.

## Grouping and Reuse

Periods may share one recommendation only when they belong to the same company
and have:

- the same exact missing targets
- the same usable semantic concept/evidence packet
- the same set of three judge models

The shared record contains the packet, prompt/model versions, three responses,
canonical comparison, and group outcome. Each covered period receives its own
application record because its selected facts and calculated value may differ.

Reuse an exact prior group when the same model lineup recurs. A different model
lineup requires a new judgment. Do not retroactively rewrite earlier groups.
Prompt-change rejudging is not part of the current policy.

Retain technical failures as immutable attempts. A caller may explicitly retry,
which appends a new attempt rather than replacing history.

## Deterministic Period Application

An unanimous recommendation does not itself create a metric. For every covered
period, deterministic code must:

1. select precedence-resolved component facts from that period
2. verify component eligibility, context, period basis, and compatible units
3. calculate the approved addition/subtraction expression, or validate the
   affirmative zero case
4. retain every source observation, relationship, validation, recommendation,
   and application reference
5. reject the application explicitly if any required component or validation
   is unavailable

The recommendation record is shared semantic reasoning. The application record
is period-specific numeric proof. Keeping them separate avoids repeating the
three model responses while preserving the exact calculation for each period.

## Metric Publication and Provenance

Direct and recovered values may coexist in `financial_metrics` because both are
base metrics consumed by downstream indicators. Their origin must remain
explicit:

- reported/direct mapping
- formula recovery
- affirmative-zero recovery

Recovered metrics must link to the immutable recommendation group and their
period application evidence. This is necessary to distinguish SEC-reported
values from calculated values and to reproduce or invalidate a recovery later.

Publish the company refresh atomically only after MS2 evidence and MS3 mapping
reach a complete result. A failure must not replace the last complete company
snapshot with partial observations or metrics.

## Learned Mapping Governance

Approved learned mappings form a reusable company concept profile:

```text
global approved mappings
  + approved mappings for the period's industries
  + approved mappings for the company's CIK
```

This profile is mapping state, not an ingestion filter. New raw evidence is
still ingested broadly. Revalidate a direct mapping against the new selected
accession and surface it for review when its meaning, statement relationship,
context, or period compatibility no longer holds.

A unanimous one-concept recovery is not automatically promoted to a direct
mapping. Promotion requires a separate governance decision.

## Segment and Quality Rules

Company-level metrics use consolidated facts. Segment or dimensional facts
remain raw evidence unless a specifically reviewed target permits them.

Use explicit states such as:

```text
found_mapped
found_unmapped
missing_target
needs_review
technical_failure
skipped_quality
segment_only
not_applicable
```

Do not silently guess malformed, conflicting, or missing values.

## Legacy Inspection Boundary

The current mapping-inspection experiment still presents active-window
`10-K`/`10-Q` formula and zero proposals for review. Those legacy proposals are
report-only: they do not populate `financial_metrics` or feed indicators.

That report must clearly identify:

- mapped and missing target metrics
- common-base versus industry-specific scope
- provider outcomes and unavailable evidence
- period coverage and active accessions
- the report-only boundary

The legacy inspection path is evidence about the current runtime, not the
accepted MS3 production recovery contract.
