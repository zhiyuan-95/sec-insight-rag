# SEC Insight RAG Financial Evidence

SEC Insight RAG turns SEC filing evidence into traceable financial metrics,
analysis, retrieval results, and cautious explanations. This glossary defines
the project language shared across those capabilities.

## Companies, Filings, and Periods

**Company**:
The SEC reporting entity being analyzed, identified by CIK and one or more
ticker symbols.
_Avoid_: Account, issuer record

**Filing**:
One SEC submission document and its metadata.
_Avoid_: Report, dataset

**Accession**:
The SEC identifier for one filing submission, including an original filing or
an amendment.
_Avoid_: Filing ID, document ID

**Original Annual Filing**:
A `10-K` that establishes the company's annual filing evidence and fiscal-period
industry-label snapshot.
_Avoid_: Base filing, initial report

**Amendment**:
A `10-K/A` that may update facts or evidence from an annual filing but does not
rewrite the corresponding industry-label snapshot.
_Avoid_: Replacement filing

**Actual Period**:
The instant date or duration dates to which a fact applies. It is distinct from
filing date, fiscal labels, and SEC frame.
_Avoid_: Reporting year

**Fiscal Period**:
The company-reported fiscal year and fiscal-period label used to group evidence
and outputs.
_Avoid_: Actual period

**Annual Structured Scope**:
Every selected Inline XBRL `10-K` and `10-K/A` accession processed by MS2/MS3,
without a fixed year window.
_Avoid_: Active window, latest five years

## XBRL Evidence and Precedence

**Raw XBRL Observation**:
One source-attributed XBRL value and its accounting context, filing lineage,
quality flags, and available semantic metadata.
_Avoid_: Base metric, normalized metric

**Source Observation**:
A raw observation preserved specifically as Arelle or SEC Company Facts
evidence before source precedence is applied.
_Avoid_: Merged fact

**Semantic Fact Identity**:
The company, concept, actual period, unit, and canonical
dimensions/consolidation state that identify the same accounting fact across
sources or accessions.
_Avoid_: Raw row key

**Arelle Structural Evidence**:
The available concept metadata, statement relationships, formula relationships,
assertions, and XBRL/SEC validation results extracted by Arelle.
_Avoid_: Metric mapping

**Precedence-Selected Observation**:
The latest valid source observation chosen for one semantic fact identity while
preserving every underlying source and conflict record.
_Avoid_: Latest filing fact

**Evidence Snapshot**:
The complete versioned company evidence state handed from annual ingestion to
metric mapping after all applicable accession attempts and precedence
selection.
_Avoid_: Filing cache, active window

**Industry-Label Snapshot**:
The immutable set of approved hard industry labels assigned to one original
annual filing and fiscal period.
_Avoid_: Current company industry

## Metrics and Mapping

**Metric Target**:
A project-owned financial concept the system attempts to populate for a fiscal
period.
_Avoid_: XBRL concept

**Base Financial Metric**:
A current business-friendly financial observation created by approved direct
mapping or a validated recovery application, with complete provenance.
_Avoid_: Raw fact, derived indicator

**Approved Mapping**:
A governed association between an observed XBRL concept and a metric target
that is allowed to create a direct base metric.
_Avoid_: Candidate mapping, semantic similarity

**Direct Mapping**:
Applying an approved mapping to one compatible precedence-selected observation.
_Avoid_: Formula recovery

**Missing Target**:
A metric target still unavailable after every eligible direct mapping has run
for the accounting context.
_Avoid_: Missing XBRL tag

**Shadow Candidate**:
A deterministic inferred concept-to-target suggestion retained for inspection
but prohibited from creating a metric or influencing judge evidence.
_Avoid_: Approved mapping

**Semantic Evidence Packet**:
The deterministic nonnumeric target and accounting evidence supplied
identically to all recovery judges.
_Avoid_: Prompt response, numeric context

**Semantic Recommendation Group**:
One or more periods sharing the same company, judge-visible semantic evidence,
exact missing-target set, and judge lineup.
_Avoid_: Period batch

**Unanimous Model Decision**:
Three independent judge responses that resolve to the same canonical formula or
zero decision for one missing target.
_Avoid_: Majority vote, consensus score

**Formula Recovery**:
A context-specific addition/subtraction expression over reported concepts used
to recover a missing target after unanimous judgment and deterministic
validation.
_Avoid_: Approved mapping, reported fact

**Zero Decision**:
A unanimous and deterministically supported conclusion that a missing target is
zero for one accounting context; absence alone is never sufficient.
_Avoid_: Default zero

**Recovery Application**:
The period-specific resolution, validation, calculation, and provenance record
for an approved semantic recommendation.
_Avoid_: Recommendation record

**Needs Review**:
A successful set of judge responses that disagrees canonically and therefore
creates no recovered metric.
_Avoid_: Technical failure

**Technical Failure**:
A missing, malformed, unavailable, or failed judge result that prevents a
canonical decision.
_Avoid_: Needs review, abstention

## Derived Evidence and Interpretation

**Derived Financial Indicator**:
A deterministic formula result calculated from base financial metrics with
formula version and source lineage.
_Avoid_: Base metric, reported fact

**Deterministic Financial Analysis**:
A reproducible trend, comparison, gap, volatility, outlier, or chart-ready
finding calculated without LLM judgment.
_Avoid_: Interpretation

**Filing Evidence**:
Source text or structured evidence preserved with accession, document, section,
and location lineage.
_Avoid_: Model context

**Retrieved Evidence**:
Filing evidence selected and ranked for a user question.
_Avoid_: Answer

**LLM Interpretation**:
A model-generated explanation or hypothesis grounded in supplied financial and
filing evidence and clearly separated from deterministic results.
_Avoid_: Fact, deterministic analysis

**Atomic Company Snapshot**:
One internally consistent published company state whose related current
evidence, metrics, provenance, and failure outcomes become visible together.
_Avoid_: Partial refresh
