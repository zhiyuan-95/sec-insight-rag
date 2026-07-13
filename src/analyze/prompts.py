"""Prompt templates for Gemini analysis belong in this module."""

from __future__ import annotations

from src.processing.company_industry_labels import HARD_INDUSTRY_LABELS

INDUSTRY_CLASSIFICATION_PROMPT_VERSION = "industry_classification_v1"
XBRL_FORMULA_PROPOSAL_PROMPT_VERSION = "xbrl_formula_proposal_v3"
XBRL_FINAL_RECOMMENDATION_PROMPT_VERSION = "xbrl_final_recommendation_v1"


def build_industry_classification_prompt(
    *,
    ticker: str,
    cik: str,
    company_name: str | None,
    sic: str | None,
    sic_description: str | None,
    business_section_text: str,
) -> str:
    """Build the Gemini prompt for 10-K Item 1 hard-industry classification."""
    labels = "\n".join(f"- {label}" for label in HARD_INDUSTRY_LABELS)
    metadata = "\n".join(
        (
            f"Ticker: {ticker}",
            f"CIK: {cik}",
            f"Company name: {company_name or 'Unknown'}",
            f"SEC SIC: {sic or 'Unknown'}",
            f"SEC SIC description: {sic_description or 'Unknown'}",
        )
    )
    return f"""You are classifying a public company into hard industry labels for a financial XBRL mapping system.

Use only these hard industry labels, exactly as written:
{labels}

Rules:
- Assign one or more labels only when the 10-K Item 1 Business text supports a material business activity in that industry.
- If the company materially operates in multiple industries, include multiple labels.
- Do not invent labels, sectors, sub-industries, or secondary labels.
- Do not classify XBRL concepts or choose SEC tags. This task only assigns company hard-industry labels.
- If the evidence is too thin or ambiguous, return an empty labels list and explain why.
- Use the SEC SIC information only as supporting context; the 10-K Item 1 Business text is the primary evidence.

Return JSON matching this schema:
{{
  "labels": ["exact hard industry label"],
  "confidence": 0.0,
  "reason": "short explanation grounded in Item 1 Business",
  "evidence_quotes": ["short quote or paraphrase from Item 1 Business"]
}}

Company metadata:
{metadata}

10-K Item 1. Business:
{business_section_text}
"""


def build_xbrl_formula_proposal_prompt(
    *,
    ticker: str,
    cik: str,
    target: dict[str, object],
    fact_pool: list[dict[str, object]],
    formula_context: dict[str, object] | None = None,
) -> str:
    """Build the prompt for one report-only missing-target formula proposal."""
    target_json = _json_block(target)
    context_json = _json_block(formula_context or {})
    facts_json = _json_block(fact_pool)
    return f"""You are proposing a report-only XBRL decision for a missing target financial metric.

The system has already tried direct catalog mapping and approved learned
mappings. Your task is not to approve a mapping. Your task is to decide whether
the missing target can be
composed from raw XBRL facts already observed for this company in the supplied
same-period context, whether the target may reasonably be zero from other
same-period evidence, or whether neither decision is supported.

Rules:
- Use only raw SEC/XBRL facts listed in the eligible same-period fact pool.
- Components may be found target facts, mapped base metric facts, approved alternates, or unknown/unmapped raw facts.
- Do not use the missing target itself as a component.
- Prefer consolidated company-level facts over dimensional or segment facts.
- All listed facts are from the period context shown below; do not mix in facts from another period.
- Clearly reason from the target_primary_statement.
- First try to build the formula using same_statement facts from that primary statement.
- If same_statement facts are insufficient, you may use unclassified_same_period facts.
- Use cross_statement facts only when no credible same-statement formula exists.
- If you use a cross_statement fact, explain why the cross-statement reference is accounting-valid in the component role or reason.
- Reference XBRL calculation/presentation logic when the listed concepts imply it; otherwise use common US GAAP presentation logic.
- Do not invent concepts, values, units, or facts.
- If the fact pool supports a credible formula, set no_formula to false, target_is_zero to false, and return formula components.
- If the missing target is reasonably zero from affirmative same-period evidence, set no_formula to false, target_is_zero to true, set formula_expression to "target = 0", and cite the supporting raw facts in components as zero evidence.
- Do not infer zero only because the target fact is missing. The supplied raw facts must provide affirmative evidence for a zero-target decision.
- If neither a credible formula nor an evidence-backed zero-target decision is supported, set no_formula to true and target_is_zero to false.
- Return exactly one best formula proposal, one zero-target decision, or one no-formula decision.
- Return JSON only. Do not include Markdown.

Return JSON matching this schema:
{{
  "no_formula": false,
  "target_is_zero": false,
  "target_metric_name": "internal metric name",
  "target_xbrl_concept": "taxonomy:Concept",
  "formula_expression": "target = + us-gaap:ComponentA - custom:ComponentB",
  "components": [
    {{
      "component_name": "plain English component name",
      "taxonomy": "us-gaap",
      "concept": "ComponentA",
      "operator": "+",
      "role": "why this component is part of the target",
      "reason": "short evidence-based reason"
    }}
  ],
  "confidence": 0.0,
  "reason": "short accounting/XBRL explanation grounded only in the fact pool",
  "uncertainty": "what could be wrong or what needs review"
}}

Company:
- ticker: {ticker}
- cik: {cik}

Missing target:
{target_json}

Formula proposal context:
{context_json}

Eligible same-period raw SEC/XBRL fact pool:
{facts_json}
"""


def build_xbrl_final_recommendation_prompt(
    *,
    ticker: str,
    cik: str,
    decision_context: dict[str, object],
) -> str:
    """Build the prompt for one period-level final recommendation choice."""
    context_json = _json_block(decision_context)
    return f"""You are choosing one report-only final recommendation for a missing financial metric.

The system has already gathered review evidence for one company, one metric, and
one reporting period. Your job is not to approve a mapping or persist a metric.
Your job is to choose exactly one final recommendation from the supplied options,
or choose no_recommendation if no option is supportable.

Rules:
- Use only the supplied options. Do not invent formulas, semantic candidates, concepts, periods, or values.
- Choose one option_id from the options list when selecting formula, semantic_candidate, or zero.
- If you choose a formula, final_recommendation must exactly equal that option's value.
- If you choose a semantic_candidate, final_recommendation must exactly equal that option's value.
- If you choose zero, final_recommendation must be exactly "0".
- Prefer a validated formula with stronger same-period evidence over a semantic candidate when the formula directly composes the target.
- Prefer semantic_candidate when formulas conflict, are weakly validated, or use questionable cross-statement evidence.
- Choose zero only when the zero option includes affirmative same-period evidence.
- If the options are contradictory or insufficient, choose no_recommendation and explain what needs review.
- Return JSON only. Do not include Markdown.

Return JSON matching this schema:
{{
  "selected_option_type": "formula",
  "selected_option_id": "formula_1",
  "final_recommendation": "target_metric = ComponentA + ComponentB",
  "confidence": 0.0,
  "reason": "short evidence-based explanation for the choice",
  "uncertainty": "what could be wrong or what needs review"
}}

Allowed selected_option_type values:
- formula
- semantic_candidate
- zero
- no_recommendation

Company:
- ticker: {ticker}
- cik: {cik}

Decision context:
{context_json}
"""


def _json_block(value: object) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True, default=str)
