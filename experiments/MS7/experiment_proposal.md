# Milestone 7 Experiment Proposal: RAG Analysis

## Purpose

This experiment should let a human inspect the complete retrieval-grounded
analysis flow. The final report should separate reported facts, derived
indicators, deterministic analytics, semantic filing evidence, and model
interpretation.

The key design goal is preventing unsupported causal claims. The output should
make it obvious what evidence was used and where interpretation begins.

## Human Question

Given a realistic user question, can I inspect how reported facts, derived
indicators, deterministic analytics, semantic filing evidence, and model
interpretation are separated in the final answer?

## Milestone Scope

This experiment covers:

- realistic user question input
- reported fact evidence inventory
- derived indicator evidence inventory
- deterministic analytics evidence inventory
- retrieved filing evidence inventory
- prompt source identification
- final answer section separation
- evidence references
- unsupported causal claim handling

This experiment does not cover SEC ingestion implementation details, indicator
formula debugging, or retrieval index debugging except through printed evidence
counts and references.

## Recommended Location

```text
experiments/MS7/
  experiment_proposal.md
  milestone7_rag_analysis.py
```

## Data Modes

Use `local` mode by default if local filings, metrics, indicators, and retrieval
indexes exist. Use `fixture` if a stable end-to-end analysis fixture is added.
Use `live` only when Gemini is intentionally called.

## Input Cases

### Case 1: Performance Question

Command:

```text
python experiments/MS7/milestone7_rag_analysis.py --ticker AAPL --question "Why did revenue change?" --mode local
```

Purpose:

Inspect how numeric evidence and filing evidence are combined.

### Case 2: Risk Question

Command:

```text
python experiments/MS7/milestone7_rag_analysis.py --ticker AAPL --question "What risks should I monitor?" --mode local
```

Purpose:

Inspect semantic filing evidence and references.

### Case 3: Unsupported Causal Question

Purpose:

Confirm the answer avoids unsupported causal claims when evidence is weak.

## Proposed Terminal Report

```text
Milestone 7 Experiment: RAG Analysis

Human Question:
  Can I inspect whether the final answer separates evidence types and avoids
  unsupported causal claims?

Run Context:
  mode: local
  ticker: AAPL
  database: stock_data.db
  filings directory: data_store/filings

User Question:
  Why did revenue change?

Evidence Inventory:
  reported facts: 3
  derived indicators: 2
  deterministic analytics findings: 2
  filing chunks: 4

Prompt Source:
  prompt file: src/analyze/prompts.py
  prompt template: ...
  model: gemini-2.5-flash

Answer Sections:
  Reported Facts:
    ...
  Derived Indicators:
    ...
  Financial Data Analysis:
    ...
  Semantic Filing Evidence:
    ...
  Interpretation:
    ...
  Evidence References:
    ...

Unsupported Claim Check:
  causal claims requiring filing support: ...
  unsupported claims removed or qualified: ...

Artifacts To Inspect:
  database table: raw_xbrl_facts
  database table: financial_metrics
  retrieval evidence: <retrieval storage path when implemented>
  prompt file: src/analyze/prompts.py

Expected Outcome:
  A human can inspect whether the answer labels each evidence type, includes
  references, and avoids claiming causality unless filing evidence supports it.
```

## Required Printed Sections

1. Human question
2. Run context
3. User question
4. Evidence inventory
5. Prompt source
6. Answer sections
7. Unsupported claim check
8. Artifacts to inspect
9. Expected outcome

## Implementation Guidance

- Keep prompt templates in `src/analyze/prompts.py`.
- Use `gemini-2.5-flash` for reasoning and answer generation.
- Keep reported facts, derived indicators, analytics results, filing evidence,
  and interpretation in separate answer sections.
- Require evidence references.
- Forbid unsupported causal claims in the prompt and in output validation.
- Do not let Gemini calculate deterministic financial metrics or indicators.

## Edge Cases To Show

- no retrieved filing evidence
- weak retrieved filing evidence
- missing indicators
- missing analytics results
- user asks for causality but filings do not support it
- evidence references are incomplete

## Expected Outcome

Milestone 7 looks healthy when the printed report lets the project owner
answer:

- What evidence types were available?
- Which prompt template was used?
- Does the answer separate facts, indicators, analytics, filing evidence, and
  interpretation?
- Are evidence references included?
- Are weak-evidence or unsupported causal claims qualified instead of stated as
  facts?
