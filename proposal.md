# Proposal: Evidence-Grounded Financial Thesis Engine

## Project Goal

SEC Insight RAG is a backend-first financial research system that helps users
understand company performance, risks, and possible drivers from SEC filings
and structured financial data.

The system should ingest authoritative evidence, calculate traceable financial
results, retrieve relevant filing text, and generate cautious explanations that
users can verify. It must distinguish reported facts, calculated metrics,
derived indicators, deterministic analysis, retrieved filing evidence, and
LLM-generated interpretation.

The project is not intended to predict stock prices or replace professional
financial advice.

## Product Direction

A user should be able to:

- initialize or refresh a public company from SEC filings
- inspect annual structured financial facts and their filing lineage
- inspect mapped base metrics and explicit missing coverage
- calculate deterministic financial indicators
- review historical trends, comparisons, gaps, and outliers
- retrieve relevant filing passages
- ask questions and receive evidence-grounded explanations
- inspect sources, formulas, uncertainty, and failure states

The first production shape remains a local Python backend with SQLite and local
filing/index storage. Cloud infrastructure, frontend work, and distributed job
systems are not required for the initial product.

## Evidence Model

Keep these evidence types distinct:

1. **Reported filing evidence**: SEC filing text and raw XBRL observations.
2. **Base financial metrics**: approved direct mappings or validated recovery
   applications with complete provenance.
3. **Derived financial indicators**: deterministic calculations over base
   metrics.
4. **Deterministic financial analysis**: trends, comparisons, gaps, volatility,
   outliers, and chart-ready findings.
5. **Retrieved filing evidence**: traceable filing passages selected for a
   question.
6. **LLM interpretation**: cautious synthesis grounded in the preceding
   evidence.

Calculated values must never be presented as reported facts. LLM statements
must never be presented as deterministic analysis. Causal claims require direct
support; otherwise the system should use uncertainty language or label the
statement as a hypothesis.

## High-Level Architecture

```text
SEC submissions and filings
  -> annual Inline XBRL ingestion and validation
  -> reconciled raw observations and structural evidence
  -> approved mapping and validated missing-metric recovery
  -> base financial metrics
  -> deterministic indicators
  -> deterministic financial analysis

SEC filing documents, including useful non-Inline documents
  -> section-aware parsing and retrieval indexes
  -> retrieved filing evidence

metrics + indicators + analysis + retrieved evidence
  -> evidence-grounded LLM analysis
  -> API/workflow outputs with citations and uncertainty
```

### Layer boundaries

- SEC/API acquisition remains separate from persistence.
- XBRL normalization, reconciliation, precedence, and mapping remain processing
  concerns.
- SQLite writes remain in storage repositories.
- Indicator and financial-analysis calculations remain deterministic and
  independent of LLM synthesis.
- Filing-text retrieval remains separate from numeric analysis.
- Workflows coordinate layers without duplicating their internals.

`docs/structure.md` owns the current implemented module map. High-fidelity
milestone designs live under `docs/milestones/`.

## Structured Financial-Data Direction

The approved structured path is annual-only:

- select every available Inline XBRL `10-K` and `10-K/A`
- use Arelle for structural extraction and XBRL/SEC validation
- retain SEC Company Facts as reconciliation and supplemental evidence
- preserve raw source observations and latest-valid precedence
- assign immutable fiscal-period industry-label snapshots
- apply approved direct mappings before recovery
- send only exact missing targets to three blind judges
- require unanimous canonical formula/zero decisions
- validate every accepted decision deterministically per period
- persist direct and recovered base metrics with different provenance

All `10-Q`/`10-Q/A` structured processing is outside this approved path.
Non-Inline annual filings may still be used by the later filing-text/RAG path.
The exact contracts are owned by MS2, MS3, and the mapping policy.

## Model and Retrieval Direction

- Use `gemini-3.1-flash-lite` for fiscal-period industry classification.
- The approved MS3 recovery panel is `gpt-5-mini`,
  `gemini-3.1-flash-lite`, and `gemini-2.5-flash`.
- Keep `gemini-2.5-flash` as the default general explanation and analysis model
  unless a later approved design changes it.
- Keep all prompt templates in `src/analyze/prompts.py`.
- Require structured, evidence-referencing outputs where the task permits.
- Use built-in LlamaIndex loaders, splitting, indexing, retrieval, and embedding
  integration when they fit; do not add custom infrastructure without need.

## Storage Direction

SQLite is the authoritative local domain store for:

- companies and filing metadata
- raw source-attributed XBRL observations
- fiscal-period industry labels
- mapping governance and provenance
- base metrics and recovery applications
- derived indicators
- deterministic analysis results
- canonical filing chunks and retrieval-generation state

Downloaded filings, Arelle result caches, vector indexes, keyword indexes,
exports, and experiment reports are local generated artifacts. Rebuildable
indexes and caches are not authoritative domain state.

Preserve lineage across every layer so a user can trace an interpretation back
through analysis, indicators, base metrics, raw facts, accessions, and filing
evidence.

## Milestone Roadmap

Milestones are capability subprojects. Each designed milestone has one durable
high-fidelity plan and independent acceptance evidence. Detailed status and
links live in `docs/milestones/README.md`.

1. **Foundation and configuration**

   Establish dependency management, settings, package boundaries, FastAPI
   health behavior, and automated testing.

2. **Annual Inline XBRL ingestion and evidence**

   Discover and process the complete selected annual history, run isolated
   Arelle validation, reconcile Company Facts, apply evidence precedence, and
   produce immutable fiscal-period industry/evidence snapshots.

3. **Base metric mapping and recovery**

   Apply approved direct mappings, identify exact missing targets, obtain
   unanimous semantic recommendations, validate them per period, and publish
   traceable base metrics atomically.

4. **Derived financial indicators**

   Calculate deterministic ratios, growth rates, margins, returns, cash-flow,
   liquidity, leverage, efficiency, and shareholder indicators from base
   metrics with formula and source lineage.

5. **Deterministic financial analysis**

   Produce structured trend, period-comparison, gap, volatility, outlier, and
   chart-ready findings. Add peer or industry benchmarks only after their
   datasets and grouping rules are approved.

6. **Filing-text ingestion and retrieval**

   Parse useful filing documents, preserve section/chunk lineage, build
   rebuildable vector and keyword indexes, and return ranked filing evidence.

7. **Evidence-grounded LLM analysis and RAG**

   Combine metrics, indicators, deterministic findings, and retrieved passages
   into grounded question answering, risk interpretation, and company thesis
   summaries.

8. **API, workflows, and end-to-end evaluation**

   Expose ingestion, metrics, indicators, analysis, retrieval, exports, and Q&A
   through thin workflows and APIs; verify end-to-end evidence quality,
   failure behavior, and operational usability.

Testing is continuous across every milestone rather than a standalone
milestone.

## Success Criteria

The product succeeds when it can:

- process one company's complete selected annual Inline XBRL history
- preserve raw observations separately from mapped/calculated values
- expose validation, reconciliation, amendment, and source precedence
- populate base metrics only through approved mappings or validated unanimous
  recovery
- keep unresolved targets and failures explicit
- calculate the approved indicator catalog with lineage and skip reasons
- produce deterministic analysis suitable for charts and later explanation
- retrieve filing passages with complete source references
- generate answers that separate evidence, calculation, analysis, and
  interpretation
- avoid unsupported causal claims and disclose weak or missing evidence
- reproduce important results from documented verification commands and local
  artifacts

## Deferred and Out of Scope

- Frontend implementation
- Macro-data ingestion
- Knowledge-graph storage
- Multi-agent orchestration
- External queues and cloud deployment infrastructure
- Stock-price prediction or personalized investment advice
- Conventional non-Inline XBRL in the structured financial-data path
- Quarterly structured-data processing under the approved MS2/MS3 design
- Automatic activation of shadow inferred mappings
- Formula operators beyond the approved addition/subtraction recovery scope
- Benchmark comparison before reliable datasets and peer rules exist

Future work may extend these boundaries only through an explicit milestone or
policy decision.
