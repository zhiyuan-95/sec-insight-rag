# SEC Insight RAG Financial Evidence

SEC Insight RAG turns reported SEC/XBRL evidence into traceable financial
metrics, indicators, and explanations while preserving the distinction between
reported and derived values.

## Language

**Accounting Context**:
The exact company/entity, period dates, unit, and dimensions/consolidation state
within which reported facts and reviewed decisions are comparable. Accession,
filing form, filing date, and fiscal labels remain provenance describing where
an observation was reported; they do not prevent valid observations from
different accessions from sharing one accounting context. A fiscal label such
as `FY2025` does not identify an accounting context by itself.
_Avoid_: Accession-bound context, period label, fiscal year alone

**Semantic Fact Identity**:
The cross-source and cross-accession identity used for reconciliation and
latest-valid-record precedence: company/entity, normalized concept, actual
instant or duration dates, unit, and canonical dimensions/consolidation state.
Accession, form, filing date, fiscal year, fiscal period, and SEC frame remain
provenance metadata rather than identity fields. The raw storage key additionally
includes accession and source so historical accessions and matching Arelle and
Company Facts observations remain separate auditable rows.
_Avoid_: Fiscal-label identity, frame identity, source-overwriting key

**Company Ingestion**:
The local workflow that incrementally acquires every available SEC 10-K Inline
XBRL filing under the designed update protocol, processes each accession with
Arelle, and preserves the resulting facts, relationships, validation
diagnostics, and lineage. It ends before metric mapping begins. Arelle is the
canonical structural and validation processor and the preferred observation
source when both it and SEC Company Facts provide the same fact identity. SEC
Company Facts is also a scoped reconciliation and supplemental observation
source for those same accessions, so Company Facts-only observations may remain
in the mapping fact pool.
Initial implementation processes accessions sequentially with a fresh isolated
child process for each accession. That child creates one Arelle Session,
processes one filing, serializes the project-owned result, closes the Session,
and terminates before the next child starts; Arelle live or global state is
never reused across filings. A concurrent process pool is deferred until
representative benchmarks demonstrate that sequential processing cannot meet
the selected deadline. Metric mapping begins only after every applicable accession has
finished ingestion, reconciliation, and latest-valid-record selection for the
atomic company snapshot; it never maps each accession independently while later
accessions are still pending.
_Avoid_: Metric mapping, indicator generation

**Local XBRL Acquisition**:
The controlled SEC client downloads each in-scope filing and its referenced
XBRL dependencies for isolated local Arelle processing. The system caches the
downloaded inputs and complete Arelle result and records source URLs, content
hashes, and relevant processor/schema versions for provenance and invalidation.
Downloaded in-scope filings and complete Arelle results are retained by default.
SQLite remains authoritative for normalized facts and published domain state,
but it does not duplicate every Arelle relationship edge or diagnostic in
dedicated tables. It stores each accession's result status, content hash,
processor/result-schema versions, and the exact evidence packet used by every
mapping decision. The complete versioned Arelle result remains in the
regenerable per-accession cache and may be cleared through an explicit manual
operation; Arelle is rerun if uncached structural evidence is later required.
Automatic LRU cleanup and
retention policies are deferred until measured disk growth justifies them.
The initial local design does not add Plan 203's separate approved-taxonomy
registry, taxonomy installer, fully portable filing-package builder, or offline
empty-cache acceptance gate; those capabilities require a later demonstrated
reproducibility or offline-operation need.
_Avoid_: Preapproved taxonomy registry, sealed offline package

**Initial Resource Guardrails**:
The first implementation uses controlled download-size checks, one isolated
Arelle worker, the measured company-workflow deadline, and rejection of
incomplete or malformed Arelle results. Plan 203's fixed limits for facts,
concepts, relationship edges, diagnostics, and serialized payload size are not
implemented until representative filing measurements demonstrate a concrete
need and support defensible thresholds.
_Avoid_: Unmeasured record-count ceiling, unrestricted worker

**First Implementation Slice**:
Implement one company's complete selected Inline XBRL `10-K` and `10-K/A`
history end to end before multi-company optimization: complete SEC submissions
discovery, sequential accession-scoped Arelle processing, Company Facts
reconciliation and supplementation, latest-valid-record selection, direct
mapping, three-judge recovery for remaining targets, and atomic persistence.
This replaces Plan 203's obsolete first assignment centered on a taxonomy
registry, portable offline packages, and one 10-K plus one 10-Q proof.
_Avoid_: 10-Q proof, optimization-first implementation, disconnected component demo

**Initial Verification Scope**:
Use focused synthetic automated tests for semantic fact identity, accession and
source precedence, duplicate handling, reconciliation, mapping compatibility,
and unanimous judge behavior. Add one human-inspectable real-company run across
that company's complete selected Inline XBRL annual history. Do not add 10-Q
fixtures, a portable offline taxonomy package, or an empty-cache offline proof
for the initial slice.
_Avoid_: Quarterly fixture, portable-package gate, test-only infrastructure expansion

**Annual Filing Scope**:
Plan 203 and this design discussion cover only the structured financial-data
pipeline from Inline XBRL ingestion through metric mapping. Every available
`10-K` and `10-K/A` accession with usable Inline XBRL enters structured database
ingestion, Arelle normalization and validation, metric mapping, formula
recovery, and numeric verification. The original and amended Inline XBRL
accessions are both preserved, while latest-valid-record precedence selects
updated facts. A non-Inline 10-K may still contain useful narrative content for
the repository's separate RAG workflow, but its acquisition, parsing, chunking,
indexing, amendment behavior, and failure handling are outside Plan 203 and the
current discussion. Non-Inline filings do not create raw XBRL facts, financial
metrics, mapping decisions, or industry-label model calls in this pipeline.
All 10-Q filings remain outside this structured scope. Annual-only structured
processing is a fixed product policy rather than a runtime configuration
toggle, so downstream mapping has no quarterly branch. Storage records and
interfaces may retain a general filing-form field for future compatibility, but
no active `enable_10q` setting or quarterly workflow exists. Plan 203 has no
structured-data "active window": the company snapshot contains all selected
Inline XBRL 10-K history without a fixed year limit. Each Inline XBRL accession's complete
Arelle result is cached after processing; normal structured-data refreshes
process only new or amended Inline XBRL 10-K accessions, subject to ordinary
cache invalidation when the filing content or processing contract changes.
Existing shared `is_active_window` fields remain temporarily for compatibility
with indicator and retrieval code outside Plan 203, but Plan 203 does not use
their values to include or exclude annual filings, facts, or metrics. Removing
those shared fields is deferred to the downstream work that owns their other
consumers.
Although the SEC Company Facts response may contain other forms and older
observations, only facts associated with the selected Inline XBRL 10-K
form-family accessions enter persistence, reconciliation, mapping, or fallback
processing.
The future annual-only schema migration removes company-level
`latest_10q_filing_date` and `next_check_date_10q` state while retaining the
general filing `form_type` field.
_Avoid_: RAG design, non-Inline filing in numeric processing, fixed-year history cutoff, current 10-Q support, inferred Q4

**Annual Filing Discovery and Routing**:
The SEC discovery step obtains the complete `10-K` and `10-K/A` history by
merging the main submissions payload's `filings.recent` arrays with every older
submissions file referenced by `filings.files`, then deduplicating by accession
number. The SEC submission record's `isInlineXBRL` value deterministically
selects accessions for Plan 203. `true` enters this structured pipeline; `false`
remains outside it without implying that the filing is useless to the separate
RAG workflow. A missing or invalid value produces a visible ingestion error for
investigation instead of triggering filename or document-content guessing.
The initial company run processes every selected Inline XBRL accession rather
than selecting only the latest filing per form. Subsequent refreshes preserve
prior results and process only newly selected original or amended accessions. A
latest-per-form selector may support scheduling or display, but it must not
limit historical structured ingestion.
_Avoid_: Recent-only history, latest-only ingestion, filename-based routing, inferred Inline XBRL status, RAG pipeline behavior

**Annual-Only Data Cleanup**:
The current workspace's persisted 10-Q and 10-Q/A filings, raw facts, dependent
metrics and indicators, quarterly-evidenced learned mappings, refresh state,
downloaded filing directories, formula cache entries, mixed generated reports,
exports, and retrieval index artifacts were removed after explicit approval.
Annual database rows and filing downloads were preserved, and paths outside the
workspace were not touched. This one-time data cleanup does not by itself change
the current runtime code; the future annual-only implementation must prevent
10-Q data from being ingested again.
_Avoid_: Inactive quarterly archive, deletion outside workspace, runtime migration

**Company Refresh Deadline**:
The wall-clock limit for the complete company workflow, including ingestion,
Arelle processing, industry classification, direct mapping, all three LLM judge
calls, deterministic recovery validation, and persistence. Plan 203's 900-second
initial and 300-second warm-refresh values are provisional because the scope now
covers all available Inline XBRL 10-Ks rather than its former fixed active
window. Final values must be selected from representative measured runs. If a
deadline expires during LLM recovery, unfinished missing targets receive a
technical-failure result without rolling back successful ingestion, direct
mappings, or completed recoveries. Indicator-generation timing is outside the
current design scope.
_Avoid_: Per-Arelle-worker timeout, LLM-excluded deadline

**Annual Refresh Schedule**:
The existing low-frequency update policy retained for annual-only operation.
The next SEC submissions check is scheduled approximately twelve months after
the latest 10-K filing date; when that due check finds no new eligible filing,
the next attempt moves to the following business day. A user may request an
explicit refresh at any time. Arelle, industry classification, and metric
mapping do not rerun unless a new or amended eligible accession or an explicitly
invalidated processing contract requires work.
There is no separate polling schedule for `10-K/A`. An amendment filed between
annual checks is discovered at the next scheduled company refresh and updates
the affected prior-period records at that time; manual refresh remains available
when earlier discovery is desired.
After a new or amended accession is processed, precedence and mapping are
reevaluated only for annual periods whose selected facts or Arelle evidence
changed. Unaffected periods retain their existing direct mappings, recovery
recommendations, applications, and provenance; the refresh does not remap the
company's complete history merely because one accession was added.
When only selected numeric fact values change, an applicable stored unanimous
semantic formula is reused and only deterministic period application and value
persistence rerun. The three judges are called again only when the affected
period's relevant concepts, LLM-visible Arelle semantic evidence, or exact
missing-target set changes.
_Avoid_: 10-Q schedule, unconditional annual reprocessing

**Atomic Company Snapshot**:
The single staged result published to consumers after a company refresh. It may
contain successful ingestion, direct mappings, completed recoveries, and
explicit technical-failure statuses for unfinished missing targets, but it is
exposed as one internally consistent version. Independent failure handling
means a recovery failure does not invalidate successful work; it does not mean
consumers can observe separate partial commits or a mixture of old and new
company state.
If changed evidence invalidates a period's prior mapping or recovery and its
replacement cannot complete, the old metric is retained only in immutable audit
history. It is not exposed as current; the new snapshot publishes that target
as missing with the applicable technical-failure or validation reason.
_Avoid_: All-or-nothing metric success, visible partial refresh

**Industry Label Assignment**:
The accession-scoped company-classification step performed once for each
in-scope 10-K Item 1 Business section with `gemini-3.1-flash-lite`. The existing
label vocabulary, prompt behavior, confidence and keep rules, multi-label
behavior, and source-controlled fallback remain unchanged, but persistence
changes from one replaceable company-wide label set to an immutable label
snapshot tied to the 10-K accession and fiscal period. Mapping for a period uses
only that period's labels; later business expansion never rewrites historical
label snapshots. A 10-K's Item 1 labels apply only to its primary fiscal year,
not to comparative prior-year facts displayed in the same filing. A later
accession or 10-K/A may replace a prior period's numeric fact under fact
precedence without replacing that period's historical industry labels; industry
classification is based only on the original 10-K and is never rerun from an
amendment. Each period's mapping targets are the deduplicated union of common
base targets and the target bundles for every industry label assigned to that
period; no primary label overrides another, and later labels do not apply
retroactively. If no approved label is available for that period after the
existing fallbacks, mapping searches only common base metric targets. The model
is configured independently as `industry_classification_model` so other LLM
tasks retain their existing model settings. This is a separate prompt and
decision from missing-metric judging and never counts as one of the three
mapping votes.
_Avoid_: XBRL validation, metric recovery

**Approved Mapping**:
A reviewed equivalence between one reported raw XBRL concept and one canonical
base financial metric.
_Avoid_: Formula mapping, recovered metric

**Target Compatibility Rules**:
The minimal deterministic safeguards applied before a raw XBRL fact may serve
one system metric. The first Plan 203 version checks only that the source is
numeric, its instant-or-duration period type is compatible, its basic unit
family such as currency or shares is compatible, its consolidation and
dimensional context is usable, and it has no blocking diagnostic. Detailed
balance-behavior policies, fine-grained numeric-type taxonomies, and additional
metric-specific contracts are deferred until observed mapping errors justify
them. These rules reject impossible candidates; they do not choose a mapping.
_Avoid_: LLM judgment, evidence score, speculative compatibility framework

**Automatic Formula Recovery**:
The metric-mapping-stage fallback for a missing target after source-controlled,
approved, and eligible Arelle-assisted direct mappings are exhausted. It runs
after filing acquisition, Arelle extraction, and XBRL validation for every
in-scope annual period, not only the latest years. Three independent LLM judges
evaluate the semantic evidence packet; a unanimous recommendation that passes
deterministic recovery validation produces a production recovered metric rather
than a report-only result. Identical semantic recommendation groups share one
judgment and stored matching recommendations are reused to control historical
processing cost.
_Avoid_: SEC ingestion, Arelle extraction, direct mapping

**Arelle Structural Evidence**:
Accession-scoped concept metadata, presentation, calculation, definition,
label, and available XBRL Formula relationships extracted by Arelle, together
with its XBRL, calculation, dimension, formula, and SEC EDGAR validation
diagnostics. SEC EDGAR/EFM validation is required canonical processing for every
in-scope 10-K accession. Arelle evidence constrains direct deterministic
mapping and informs LLM recovery, but does not itself choose a project metric or
expose numeric values to an LLM judge. Missing, incomplete, or truncated
required evidence cannot activate an inferred direct mapping. LLM recovery may
still use an explicitly labeled Arelle-unavailable fallback packet.
Fatal filing or DTS diagnostics block the accession; a diagnostic tied to a
specific fact or relationship blocks only that evidence; warnings remain
visible to the judges without blocking recommendations.
_Avoid_: LLM recommendation, internal metric mapping

**Arelle Result Status**:
An accession result is either `complete` or `failed`. `complete` means a
trustworthy core fact set was returned; ordinary warnings, missing optional
relationships, and evidence-specific blocking diagnostics remain attached to
the individual evidence and do not create an accession-level degraded state.
`failed` means no trustworthy Arelle result can be used and activates the
explicitly labeled Company Facts fallback. There is no ambiguous top-level
`degraded` result.
_Avoid_: Accession-level partial trust, warning-as-failure

**Arelle-Unavailable Recovery**:
An exceptional fallback used only after an attempted Arelle run fails because
the filing, downloaded data, parser, or program needs investigation. All three
judges may still receive the available Company Facts concept pool with an
explicit `arelle_evidence_unavailable` status; no Arelle relationships are
invented. Record the underlying error and the missing-evidence provenance, but
do not add a separate automatic retry or revalidation workflow for this rare
case. Reprocess it explicitly after the cause is understood.
_Avoid_: Normal alternate pipeline, fabricated Arelle evidence, skipped Arelle attempt

**Canonical Formula**:
A normalized formula signature used to compare judge recommendations. It uses
exact taxonomy-qualified concept identifiers and operators, ignores response
wording and confidence scores, and normalizes mathematically harmless ordering
such as `A + B` versus `B + A`. A different concept or operator is a different
formula.
_Avoid_: Verbatim model response, semantic approximation

**Formula Pattern**:
A reusable expression over named XBRL concepts, proposed from their semantics
and accounting relationships rather than their numeric values. It may be
suggested in more than one accounting context, but carries no approval; every
context requires its own unanimous model decision before producing a recovered
metric. Recovery formulas are limited to addition and subtraction of reported
concepts; multiplication, division, constants, ratios, and percentages are out
of scope.
_Avoid_: Approved formula, recovered metric

**Financial Metric Observation**:
The current usable company-and-period value for one canonical target metric,
stored in `financial_metrics` whether it came from direct mapping or formula
recovery. A directly mapped observation points to its raw fact; a recovered
observation points to its period-specific recovery application record.
_Avoid_: Target definition, derived indicator

**Deterministic Recovery Validation**:
The post-consensus step that resolves each recommended concept within the
current statement evidence set, rejects blocking Arelle diagnostics, checks
compatible period context, units, and consolidation scope, and then evaluates
the formula. A failed check produces an invalid proposal and no metric; numeric
values are not exposed to the judges.
_Avoid_: Semantic judgment, model validation

**Deterministic Inferred Mapping**:
A one-concept-to-target mapping selected by project-owned hard gates and scoring
over Arelle structural evidence after hard and previously approved mappings are
exhausted. It runs before formula recovery and uses no LLM judgment. It begins
in shadow-only mode: candidates are inspectable but cannot populate
`financial_metrics`, so unresolved targets continue to formula recovery. An
inferred mapping is company-scoped and may be activated only after a
representative human-reviewed evaluation demonstrates acceptable precision; a
later accession still requires deterministic revalidation. The final evaluation
sample and coverage requirements will be selected from observed results rather
than Plan 203's currently unproven fixed `60 companies / 300 decisions` counts.
_Avoid_: Formula recovery, semantic model mapping

**Duplicate Fact Occurrence**:
More than one physical occurrence with the same concept, context, unit, and
dimensions. Occurrences with equivalent normalized values are collapsed
deterministically into one raw observation with an occurrence count and compact
source references. No separate occurrence-ledger table is added. Conflicting
same-accession values retain compact conflict evidence, are quarantined, and
cannot populate a metric.
_Avoid_: Automatic ambiguity, silent conflict resolution

**Invalid Proposal**:
An auditable rejection recorded when the judges agree on a formula pattern or
zero decision but its deterministic validation fails. It retains the failed
proposal and validation evidence but produces no metric.
_Avoid_: Needs review, technical failure

**Independent Judgment**:
One judge model's recommendation made from the same missing target and period
concept set as the other judges, without seeing their recommendations. Consensus
is calculated only after all three independent responses are complete. The
three calls for one semantic group run concurrently to reduce wall-clock time;
this changes neither their input nor token usage. Judges receive the underlying
Arelle evidence but not shadow-only inferred-mapping candidates or scores,
which remain separate evaluation records and cannot anchor the semantic
recommendations.
Each judge returns one structured result per missing target: `formula`, `zero`,
or `no_formula`; exact eligible component identifiers and `+`/`-` operators
when applicable; cited evidence IDs; and a short accounting rationale. Numeric
values and free-form-only answers are prohibited so canonical agreement can be
computed deterministically.
_Avoid_: Debate, sequential anchoring

**Missing Target Metric**:
A canonical base metric that remains unavailable for one accounting context
after deterministic catalog mapping and approved learned mappings have both
been applied to the concepts provided for that period. Only missing target
metrics may enter LLM-assisted recovery.
_Avoid_: Successfully mapped metric, every absent raw concept

**Metric Mapping Pipeline**:
The post-ingestion process that consumes the complete precedence-resolved atomic
company snapshot and maps raw XBRL concepts into system target metrics. Phase
one performs direct metric mapping with governed and
Arelle-assisted deterministic evidence. Phase two asks three independent LLM
judges for recommendations only for targets still missing, using the structured
Arelle evidence packet. Ingestion results and successful mappings remain valid
when a recovery fails, and the resulting successes and explicit failures are
staged and published together as one atomic company snapshot. Indicator
generation is downstream and outside the current design scope.
_Avoid_: SEC ingestion, indicator calculation

**Current Statement Evidence Set**:
The accession-aware evidence selected for one company, statement, and period.
Statement relationships follow statement-level precedence: a newer accession
replaces presentation, calculation, definition, or formula evidence only for a
statement network it validly provides. Omission of a network from a partial
amendment does not erase the valid original network. Numeric observations use
fact-identity precedence: a later valid record replaces the same fact identity,
but omission does not erase an earlier valid record. Formula application resolves precedence independently for each
component, so a valid component updated by a partial amendment may be combined
with another still-valid component retained from the original filing when both
share the required period and accounting context. Every component keeps its own
accession provenance.
Concept labels, documentation, and other semantic metadata use field-level
precedence: a newer valid value replaces its earlier counterpart, while a
missing field in an amendment does not erase earlier valid metadata. Each
retained metadata field preserves its source accession.
_Avoid_: Whole-filing replacement, untracked accession mixing

**Semantic Recovery Recommendation**:
A formula pattern, zero recommendation, or abstention produced for a missing
target from the names, labels, definitions, and accounting relationships of the
XBRL concepts provided for that period. Numeric fact values are not part of the
LLM judgment. A recommendation is not rejected solely because Arelle does not
supply an explicit relationship for it; the judges may apply accounting
knowledge to the concepts shown. A period application still fails when a
required component concept has no usable source fact.
_Avoid_: Numeric validation, direct mapping pass

**Semantic Evidence Packet**:
The identical, compact, non-numeric input sent to each judge. A versioned
deterministic packet builder selects the relevant statement and target
neighborhoods from the complete Arelle result and supplies stable evidence IDs
that link back to it. A group batch contains the exact missing-target set,
shared statement evidence, and focused evidence neighborhoods for each target.
It includes target definitions and statement types; presentation hierarchy;
calculation edges and weights; definition and dimension relationships;
available XBRL Formula rules and assertion results; labels and documentation;
and validation diagnostics. US-GAAP and SEC taxonomy concepts are prioritized;
available company-extension concepts may remain candidates when they carry
relevant company-specific meaning. A cross-statement concept may be used only
when the recommendation explains a valid accounting relationship. Both mapped
and unmapped period concepts may be components; existing mappings remain
unchanged. A concept is eligible as a formula component only when it has a
usable, precedence-selected source fact for the applicable period. Related
concepts without such a fact may appear as clearly marked structural context
but cannot be selected as components. Unavailable metadata remains absent and
is never invented.
_Avoid_: Numeric fact packet, model-specific context

**Semantic Recommendation Group**:
Annual periods within one company's available 10-K history whose LLM-visible
semantic evidence packets are identical for the same statement and exact set of
missing targets.
Numeric values, units, dates, fiscal labels, accessions, and raw fact IDs do not
affect grouping. The three judges run once for the group and their recommendation
is distributed to its periods; deterministic validation and calculation still
run separately for every period. A later refresh may reuse the recommendation
for a newly processed period only when the visible evidence, missing-target set,
and three-model judge lineup still match. A changed judge lineup requires a new
judgment for the new period; it does not retroactively rejudge historical
periods unless an explicit reprocessing or backfill operation requests that.
_Avoid_: Numeric-period batch, fuzzy evidence match

**Recovered Metric**:
A value produced for one accounting context by either an evaluated formula
pattern or a zero decision after a unanimous model decision. Its source facts,
formula or zero rationale, validation evidence, and judge decisions remain its
provenance. It is available to downstream deterministic indicators for that
context, but its approval cannot be reused in another context. Recovery is
never proposed for a successfully mapped metric. A recovered value may use one
raw concept, but that context-specific decision does not create a reusable
approved mapping.
_Avoid_: Reported fact, approved mapping

**Reconciliation Conflict**:
An unresolved disagreement between normalized Arelle and SEC Company Facts
observations for the same fact identity. Both sources and their diagnostics are
retained, but a valid Arelle observation remains canonical and eligible for
mapping or recovery. Company Facts neither overwrites nor quarantines it; only
a blocking Arelle or project validation result can do so. The conflict remains
visible for investigation instead of silently changing the metric value.
_Avoid_: Company Facts precedence, hidden mismatch, automatic correction

**Company Facts Supplemental Observation**:
An observation associated with a selected Inline XBRL accession that is
available from SEC Company Facts but has no matching fact extracted by Arelle.
Raw Arelle and Company Facts observations remain separate immutable source
records with their own lineage; neither source row is overwritten or physically
merged. The combined mapping pool is a precedence-resolved view over those
records. The future Plan 203 schema migration adds `source` to the
`raw_xbrl_facts` observation identity/unique key; the current key omits it and
would otherwise overwrite matching Arelle and Company Facts rows. This uses the
existing raw-fact table rather than adding a second source-specific fact table.
It remains in the normal period mapping pool rather than being discarded merely
because the Arelle filing load otherwise completed. It is explicitly labeled as
Company Facts-sourced, must pass the same minimal target-compatibility checks,
and carries `arelle_fact_unavailable` rather than invented Arelle fact evidence.
Fact availability and structural-evidence availability are tracked separately:
when Arelle's DTS and relationship networks contain that concept, its real
labels, documentation, and relationships remain available to mapping and the
judges even though the selected numeric observation comes from Company Facts.
Structural evidence is labeled unavailable only when Arelle truly lacks it.
Semantic metadata is assembled field by field: valid Arelle labels,
documentation, and related fields are preferred, while Company Facts may fill
only fields that Arelle leaves missing. Every retained field records its source;
this metadata union never combines, averages, or changes numeric observations.
It is usable only when accession, form, period, and unit resolve to one
compatible value. Across different accessions, the latest valid accession
observation replaces the earlier observation for the same semantic fact
identity. Exact duplicates collapse with lineage retained. Conflicting values
that remain within the same accession and accounting identity are quarantined
because accession precedence cannot distinguish them.
When both sources provide the same identity, valid Arelle remains canonical;
when they conflict, the conflict is recorded and valid Arelle remains selected.
Cross-accession selection applies in this order: choose the latest valid
accession that actually reports the semantic fact, then prefer Arelle within
that accession when its observation is valid; otherwise use its unambiguous
Company Facts observation. When a blocking diagnostic disqualifies the Arelle
observation, the selected Company Facts observation retains an
`arelle_fact_blocked` marker and the blocking diagnostic in provenance.
Omission from a later accession does not erase the earlier selected observation.
_Avoid_: Fabricated Arelle evidence, silent source merge, discarded Company Facts-only observation

**Semantic Recommendation Record**:
An immutable group-level record containing the semantic evidence packet, all
three independent judge responses, and their canonical formula, validated-zero,
or abstention outcome. It is stored once for all periods in the semantic
recommendation group.
_Avoid_: Period calculation, duplicated judge output

**Recovery Application Record**:
An immutable period-specific application of one semantic recommendation. It
records the selected source facts, accounting context, deterministic validation,
calculated value, and failure reason when applicable. Each recovered financial
metric points to its successful application; one period may fail even when
other periods sharing the recommendation succeed.
_Avoid_: Shared semantic judgment, reported fact

**Needs Review**:
A non-passing result recorded when all three judge models respond successfully
but do not agree on the same validated formula pattern, zero decision, or
abstention. It produces no metric.
_Avoid_: Approved decision, technical failure

**Technical Failure**:
A retryable non-decision recorded when at least one judge model is unavailable
or its request fails. It affects only the missing targets in that failed request,
produces no recovered metric for them, and is not a needs-review result.
Successful ingestion, direct mappings, and other recovery results remain valid.
_Avoid_: Model disagreement, unanimous abstention

**Zero Decision**:
A conclusion that a metric is zero for one accounting context, accepted only
when all three judge models agree and each decision has deterministically
validated affirmative evidence. The cited facts and an explicit accounting
relationship must deterministically entail that the target equals zero; the
mere presence of numeric facts is insufficient. Absence of a reported fact is
not evidence of zero. Judges may recommend zero without seeing raw amounts only
when their shared evidence packet includes an explicit Arelle-backed
`zero_entailment_validated` result.
_Avoid_: Missing fact, zero mapping

**Unanimous Model Decision**:
A semantic-group decision in which all three judge models return the same
canonical recovery recommendation. It authorizes applying that recommendation
to each grouped period, but a recovered metric is produced only where that
period's deterministic validation succeeds. Any disagreement, unavailable
judge, or provider failure prevents approval. The three judge models are not
currently required to come from distinct providers. Three `no_formula`
responses are a unanimous abstention: they produce no metric and grant no
approval.
_Avoid_: Majority consensus, model recommendation
