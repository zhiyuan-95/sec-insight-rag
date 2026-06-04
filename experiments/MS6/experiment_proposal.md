# Milestone 6 Experiment Proposal: Gemini Integration

## Purpose

This experiment should let a human inspect Gemini configuration, prompt source,
prompt rendering, and call metadata. It should prove that LLM reasoning is
configured correctly without blending it with deterministic financial
calculations.

## Human Question

When the system calls Gemini, can I inspect the configured model, prompt source,
task type, latency, and usage metadata without mixing this with deterministic
financial calculations?

## Milestone Scope

This experiment covers:

- Gemini provider configuration
- default model validation
- prompt template location
- rendered prompt preview
- controlled call metadata
- secret-safe configuration output

This experiment does not cover deterministic calculation correctness,
retrieval-grounded answer quality, or final RAG synthesis.

## Recommended Location

```text
experiments/MS6/
  experiment_proposal.md
  milestone6_gemini_integration.py
```

## Data Modes

The experiment should support:

```text
fixture
  Renders prompts and fake call metadata without contacting Gemini.

live
  Sends a small controlled prompt to Gemini.
  Must require a configured Gemini key.
```

Default mode should be `fixture`.

## Input Cases

### Case 1: Fixture Prompt Rendering

Command:

```text
python experiments/MS6/milestone6_gemini_integration.py --mode fixture
```

Purpose:

Inspect prompt source and rendered prompt shape without a live Gemini call.

### Case 2: Live Gemini Call

Command:

```text
python experiments/MS6/milestone6_gemini_integration.py --mode live
```

Purpose:

Inspect provider call metadata with a small controlled prompt.

### Case 3: Unsupported Model Configuration

Purpose:

Show model validation behavior.

## Proposed Terminal Report

```text
Milestone 6 Experiment: Gemini Integration

Human Question:
  Can I inspect model configuration, prompt loading, and Gemini call metadata?

Run Context:
  mode: fixture
  env file: config.env

Configuration:
  provider: Gemini
  primary model: gemini-2.5-flash
  allowed model: gemini-2.5-flash
  Gemini key configured: yes/no
  prompt file: src/analyze/prompts.py

Prompt Preview:
  task type: filing_summary
  prompt template name: ...
  first 500 characters:
    ...

Call Metadata:
  mode: fixture
  provider: Gemini
  model: gemini-2.5-flash
  task type: filing_summary
  latency ms: ...
  token usage: ...

Artifacts To Inspect:
  source module: src/analyze/prompts.py
  source module: src/analyze/
  source module: src/config/settings.py

Expected Outcome:
  A human can confirm the configured model, prompt source, and call metadata.
  Deterministic calculations are not delegated to Gemini.
```

## Required Printed Sections

1. Human question
2. Run context
3. Configuration
4. Prompt preview
5. Call metadata
6. Artifacts to inspect
7. Expected outcome

## Implementation Guidance

- Use `gemini-2.5-flash` as the only default model.
- Keep all prompt templates in `src/analyze/prompts.py`.
- Do not define prompt strings inline in the experiment script.
- Do not print API keys or secrets.
- Do not perform deterministic financial calculations through Gemini.

## Edge Cases To Show

- Gemini key missing in live mode
- unsupported model configured
- prompt template missing
- live call fails
- usage metadata unavailable

## Expected Outcome

Milestone 6 looks healthy when the printed report lets the project owner
answer:

- Which provider and model are configured?
- Is the model `gemini-2.5-flash`?
- Which prompt template was used?
- Where did the prompt come from?
- Was a Gemini call made or only simulated?
- Are call metadata and latency visible without exposing secrets?
