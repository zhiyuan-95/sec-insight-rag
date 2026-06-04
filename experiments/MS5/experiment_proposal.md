# Milestone 5 Experiment Proposal: Retrieval Pipeline

## Purpose

This experiment should let a human inspect filing chunking and retrieval before
retrieved evidence is used in analysis. The report should show chunk counts,
metadata, retrieved results, scores, source paths, and readable previews.

## Human Question

If filing text exists locally, can I inspect how it was chunked and whether
retrieval returns relevant evidence with useful filing metadata?

## Milestone Scope

This experiment covers:

- filing document loading
- text splitting and chunk creation
- retrieval index creation or loading
- retrieval for realistic financial questions
- chunk metadata preservation
- retrieved chunk previews

This experiment does not cover deterministic financial analytics, Gemini calls,
or final RAG answer synthesis.

## Recommended Location

```text
experiments/MS5/
  experiment_proposal.md
  milestone5_retrieval_pipeline.py
```

## Data Modes

Use `local` mode by default. Retrieval should read local filing files from
`data_store/filings/`. Use `fixture` if stable filing text fixtures are added.

## Input Cases

### Case 1: Performance Query

Command:

```text
python experiments/MS5/milestone5_retrieval_pipeline.py --ticker AAPL --query "revenue change" --mode local
```

Purpose:

Inspect retrieval for management discussion and financial evidence.

### Case 2: Risk Query

Command:

```text
python experiments/MS5/milestone5_retrieval_pipeline.py --ticker AAPL --query "supply chain risk" --mode local
```

Purpose:

Inspect retrieval for risk factor evidence.

### Case 3: Weak Or Empty Query

Purpose:

Show weak or empty retrieval results clearly.

## Proposed Terminal Report

```text
Milestone 5 Experiment: Retrieval Pipeline

Human Question:
  Can I inspect filing chunks and retrieved evidence for a realistic question?

Run Context:
  mode: local
  ticker: AAPL
  query: revenue change
  filings directory: data_store/filings

Chunking Summary:
  ticker  form  filing date  chunks created  sections found
  AAPL    10-K  ...          ...             MD&A, Risk Factors, Notes
  AAPL    10-Q  ...          ...             MD&A

Top Retrieved Chunks:
  rank  score  form  filing date  section       accession number  source path
  1     ...    10-K  ...          MD&A          ...               ...
  2     ...    10-Q  ...          Risk Factors  ...               ...

Chunk Preview:
  rank 1:
    <first readable excerpt of retrieved chunk>

Artifacts To Inspect:
  filing directory: data_store/filings
  retrieval storage: <index path when implemented>
  source module: src/retrieval/

Expected Outcome:
  A human can inspect chunk counts, metadata, retrieved sections, scores, source
  paths, and text previews before chunks are passed into analysis.
```

## Required Printed Sections

1. Human question
2. Run context
3. Chunking summary
4. Top retrieved chunks
5. Chunk preview
6. Artifacts to inspect
7. Expected outcome

## Implementation Guidance

- Use built-in LlamaIndex document loading, splitting, indexing, or retrieval
  tools when they fit the task.
- Use `SentenceSplitter` as the default splitter only when it fits the filing
  text.
- Preserve metadata: ticker, CIK, form, filing date, section, accession number,
  and source path.
- Do not use Gemini to judge retrieval quality.

## Edge Cases To Show

- no local filing files exist
- filing text cannot be loaded
- no chunks are produced
- query returns weak or empty results
- retrieved chunks have missing metadata
- section detection is unavailable

## Expected Outcome

Milestone 5 looks healthy when the printed report lets the project owner
answer:

- Which filings were chunked?
- How many chunks were created?
- Which sections were found?
- Which chunks were retrieved for the query?
- Do retrieved chunks carry useful metadata?
- Can the user read a preview and judge relevance?
