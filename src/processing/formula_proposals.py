"""Report-only validation for LLM-proposed XBRL recovery formulas."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

FORMULA_PROPOSAL_PROMPT_VERSION = "xbrl_formula_proposal_v3"
FORMULA_CONTEXT_FINGERPRINT_VERSION = "formula_context_v1"
FORMULA_PROPOSAL_CACHE_SCHEMA_VERSION = "formula_proposal_cache_v1"
STATEMENT_BUCKET_CLASSIFIER_VERSION = "statement_bucket_v1"
TARGET_CATALOG_VERSION = "target_catalog_v1"

PROVIDER_STATUS_PROPOSED = "proposed"
PROVIDER_STATUS_TARGET_ZERO = "target_zero"
PROVIDER_STATUS_NO_FORMULA = "no_formula"
PROVIDER_STATUS_UNAVAILABLE = "provider_unavailable"
PROVIDER_STATUS_FAILED = "provider_failed"

VALIDATION_STATUS_VALIDATED = "validated_component_pool"
VALIDATION_STATUS_ZERO_EVIDENCE = "validated_zero_evidence_pool"
VALIDATION_STATUS_FAILED = "validation_failed"
VALIDATION_STATUS_NOT_APPLICABLE = "not_applicable"

VALIDATION_SKIP_ZERO_TARGET_NO_EVIDENCE = "zero_target_no_evidence_components"
VALIDATION_SKIP_NO_COMPONENTS = "formula_proposal_no_components"
VALIDATION_SKIP_OUTSIDE_FACT_POOL = "formula_component_outside_raw_fact_pool"
VALIDATION_SKIP_CIRCULAR_COMPONENT = "formula_component_uses_missing_target"
VALIDATION_SKIP_NO_NUMERIC_VALUES = "formula_component_has_no_numeric_values"
VALIDATION_SKIP_NO_COMMON_PERIOD_UNIT = "formula_components_no_common_period_unit"
VALIDATION_SKIP_DUPLICATE_FACTS = "formula_components_duplicate_same_period_facts"
VALIDATION_SKIP_CROSS_STATEMENT_EXPLANATION = "formula_cross_statement_component_missing_explanation"

CONSENSUS_VALIDATED = "model_consensus_validated"
CONSENSUS_TARGET_ZERO = "model_consensus_target_zero"
CONSENSUS_SINGLE_VALIDATED = "single_model_validated"
CONSENSUS_SINGLE_TARGET_ZERO = "single_model_target_zero"
CONSENSUS_DISAGREEMENT = "model_disagreement_needs_review"
CONSENSUS_NOT_APPLICABLE = "no_validated_formula_consensus"

CACHE_STATUS_GENERATED_NEW = "generated_new"
CACHE_STATUS_REUSED_EXACT_CONTEXT = "reused_exact_context"
CACHE_STATUS_REUSED_VALIDATION_FAILED = "reused_but_validation_failed"
CACHE_STATUS_UNAVAILABLE = "cache_unavailable"
CACHE_STATUS_ENTRY_INVALID = "cache_entry_invalid"

STATEMENT_RELATIONSHIP_SAME = "same_statement"
STATEMENT_RELATIONSHIP_UNCLASSIFIED = "unclassified_same_period"
STATEMENT_RELATIONSHIP_CROSS = "cross_statement"

_UNIT_FAMILY_MONETARY = "monetary"
_UNIT_FAMILY_SHARES = "shares"
_UNIT_FAMILY_PER_SHARE = "per_share"

_MONETARY_STATEMENT_TYPES = {
    "balance_sheet",
    "cash_flow_statement",
    "income_statement",
}
_COMMON_CURRENCY_UNITS = {
    "AUD",
    "BRL",
    "CAD",
    "CHF",
    "CNY",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "ILS",
    "INR",
    "JPY",
    "KRW",
    "MXN",
    "NOK",
    "SEK",
    "SGD",
    "TWD",
    "USD",
    "ZAR",
}


class FormulaProposalComponentResponse(BaseModel):
    """One raw XBRL concept used in a proposed formula."""

    component_name: str = ""
    taxonomy: str = ""
    concept: str = ""
    operator: str = "+"
    role: str = ""
    reason: str = ""

    @field_validator("operator")
    @classmethod
    def normalize_operator(cls, value: str) -> str:
        clean = str(value or "+").strip()
        return clean if clean in {"+", "-"} else "+"

    @field_validator("component_name", "taxonomy", "concept", "role", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return str(value or "").strip()


class FormulaProposalResponse(BaseModel):
    """Structured model response for one missing target formula proposal."""

    no_formula: bool = False
    target_is_zero: bool = False
    target_metric_name: str = ""
    target_xbrl_concept: str = ""
    formula_expression: str = ""
    components: list[FormulaProposalComponentResponse] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    uncertainty: str = ""

    @field_validator("target_metric_name", "target_xbrl_concept", "formula_expression", "reason", "uncertainty")
    @classmethod
    def strip_response_text(cls, value: str) -> str:
        return str(value or "").strip()


@dataclass(frozen=True)
class FormulaProposalFact:
    """One eligible raw SEC/XBRL fact available to the formula proposal panel."""

    raw_fact_id: int
    taxonomy: str
    concept: str
    label: str
    value_numeric: Decimal | None
    unit: str
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    accession_number: str
    form: str
    start_date: date | None = None
    end_date: date | None = None
    filed_date: date | None = None
    mapping_status: str = "unknown_unmapped"
    mapped_metric_name: str = ""
    mapped_statement_type: str = ""

    @property
    def concept_key(self) -> tuple[str, str]:
        return (_normalize_key_part(self.taxonomy), _normalize_key_part(self.concept))

    @property
    def period_unit_key(self) -> tuple[str, str, int | None, str]:
        return (
            self.unit.strip(),
            self.period_type.strip(),
            self.fiscal_year,
            (self.fiscal_period or "").strip().upper(),
        )

    @property
    def period_context_key(self) -> tuple[str, str, str, int | None, str, str]:
        return (
            self.accession_number.strip(),
            self.unit.strip(),
            self.period_type.strip(),
            self.fiscal_year,
            (self.fiscal_period or "").strip().upper(),
            self.form.strip(),
        )


@dataclass(frozen=True)
class FormulaProposalTarget:
<<<<<<< HEAD
    """One target still unresolved after direct and approved learned mapping."""
=======
    """One target still unresolved after hard mapping."""
>>>>>>> 22949cb (Remove obsolete milestone 2.5 artifacts)

    target_metric_name: str
    target_xbrl_concept: str
    taxonomy: str
    concept: str
    statement_type: str
    industry_label: str = ""
    notes: str = ""

    @property
    def concept_key(self) -> tuple[str, str]:
        return (_normalize_key_part(self.taxonomy), _normalize_key_part(self.concept))


@dataclass(frozen=True)
class FormulaProposalContext:
    """One raw-concept pool context for report-only formula proposal."""

    context_id: str
    target_primary_statement: str
    period_context: dict[str, object]
    facts: tuple[FormulaProposalFact, ...]
    prompt_fact_pool: tuple[dict[str, object], ...]
    statement_relationship_by_key: dict[tuple[str, str], str]
    base_fingerprint_payload: dict[str, object]


@dataclass(frozen=True)
class _FormulaProposalPeriodGroup:
    """One same-period candidate pool before identical pools are collapsed."""

    facts: tuple[FormulaProposalFact, ...]
    period_context: dict[str, object]
    prompt_fact_pool: tuple[dict[str, object], ...]
    statement_relationship_by_key: dict[tuple[str, str], str]


@dataclass(frozen=True)
class FormulaProposalProviderResult:
    """One provider's report-only formula proposal for one target."""

    provider_name: str
    model_name: str
    target_metric_name: str
    target_xbrl_concept: str
    provider_status: str
    no_formula: bool
    target_is_zero: bool
    formula_expression: str
    components: tuple[FormulaProposalComponentResponse, ...]
    confidence: float
    reason: str
    uncertainty: str
    prompt_version: str = FORMULA_PROPOSAL_PROMPT_VERSION
    error: str = ""


@dataclass(frozen=True)
class FormulaProposalValidationResult:
    """Deterministic validation result for one model proposal."""

    validation_status: str
    skip_reason: str
    valid_component_count: int
    invalid_components: tuple[str, ...] = ()
    circular_components: tuple[str, ...] = ()
    matched_raw_fact_ids: tuple[int, ...] = ()
    matched_accession_numbers: tuple[str, ...] = ()
    common_period_units: tuple[str, ...] = ()
    notes: str = ""


FORMULA_PROPOSAL_RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "no_formula",
        "target_is_zero",
        "target_metric_name",
        "target_xbrl_concept",
        "formula_expression",
        "components",
        "confidence",
        "reason",
        "uncertainty",
    ],
    "properties": {
        "no_formula": {"type": "boolean"},
        "target_is_zero": {"type": "boolean"},
        "target_metric_name": {"type": "string"},
        "target_xbrl_concept": {"type": "string"},
        "formula_expression": {"type": "string"},
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["component_name", "taxonomy", "concept", "operator", "role", "reason"],
                "properties": {
                    "component_name": {"type": "string"},
                    "taxonomy": {"type": "string"},
                    "concept": {"type": "string"},
                    "operator": {"type": "string", "enum": ["+", "-"]},
                    "role": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "uncertainty": {"type": "string"},
    },
}

def provider_unavailable_result(
    *,
    provider_name: str,
    model_name: str,
    target: FormulaProposalTarget,
    reason: str,
) -> FormulaProposalProviderResult:
    """Return a report row for a provider that cannot run."""
    return FormulaProposalProviderResult(
        provider_name=provider_name,
        model_name=model_name,
        target_metric_name=target.target_metric_name,
        target_xbrl_concept=target.target_xbrl_concept,
        provider_status=PROVIDER_STATUS_UNAVAILABLE,
        no_formula=True,
        target_is_zero=False,
        formula_expression="",
        components=(),
        confidence=0.0,
        reason="",
        uncertainty="",
        error=reason,
    )


def provider_failed_result(
    *,
    provider_name: str,
    model_name: str,
    target: FormulaProposalTarget,
    error: str,
) -> FormulaProposalProviderResult:
    """Return a report row for a provider call or parse failure."""
    return FormulaProposalProviderResult(
        provider_name=provider_name,
        model_name=model_name,
        target_metric_name=target.target_metric_name,
        target_xbrl_concept=target.target_xbrl_concept,
        provider_status=PROVIDER_STATUS_FAILED,
        no_formula=True,
        target_is_zero=False,
        formula_expression="",
        components=(),
        confidence=0.0,
        reason="",
        uncertainty="",
        error=error,
    )


def provider_result_from_response(
    *,
    provider_name: str,
    model_name: str,
    target: FormulaProposalTarget,
    response: FormulaProposalResponse,
) -> FormulaProposalProviderResult:
    """Normalize a structured model response into report evidence."""
    no_formula = bool(response.no_formula)
    target_is_zero = bool(response.target_is_zero) and not no_formula
    if target_is_zero:
        provider_status = PROVIDER_STATUS_TARGET_ZERO
    elif no_formula:
        provider_status = PROVIDER_STATUS_NO_FORMULA
    else:
        provider_status = PROVIDER_STATUS_PROPOSED
    return FormulaProposalProviderResult(
        provider_name=provider_name,
        model_name=model_name,
        target_metric_name=response.target_metric_name or target.target_metric_name,
        target_xbrl_concept=response.target_xbrl_concept or target.target_xbrl_concept,
        provider_status=provider_status,
        no_formula=no_formula,
        target_is_zero=target_is_zero,
        formula_expression=response.formula_expression,
        components=tuple(response.components),
        confidence=float(response.confidence),
        reason=response.reason,
        uncertainty=response.uncertainty,
    )


def coerce_formula_proposal_response(payload: object) -> FormulaProposalResponse:
    """Coerce a provider payload into the shared formula proposal schema."""
    if isinstance(payload, FormulaProposalResponse):
        return payload
    if isinstance(payload, BaseModel):
        payload = payload.model_dump()
    if isinstance(payload, str):
        payload = json.loads(_extract_json_text(payload))
    if not isinstance(payload, dict):
        raise ValueError("formula proposal provider returned a non-object payload")
    return FormulaProposalResponse.model_validate(payload)


def build_formula_proposal_contexts(
    *,
    target: FormulaProposalTarget,
    fact_pool: tuple[FormulaProposalFact, ...],
) -> tuple[FormulaProposalContext, ...]:
    """Build one prompt context per distinct raw-concept pool for one target."""
    if not fact_pool:
        return ()

    preferred_period_type = _preferred_period_type_for_statement(target.statement_type)
    preferred_facts = tuple(
        fact
        for fact in fact_pool
        if preferred_period_type and _normalize_key_part(fact.period_type) == preferred_period_type
    )
    eligible_facts = preferred_facts or fact_pool
    unit_compatible_facts = _target_unit_compatible_facts(target=target, facts=eligible_facts)
    if unit_compatible_facts:
        eligible_facts = unit_compatible_facts

    grouped: dict[tuple[str, str, str, int | None, str, str], list[FormulaProposalFact]] = {}
    for fact in eligible_facts:
        grouped.setdefault(fact.period_context_key, []).append(fact)

    period_groups: list[_FormulaProposalPeriodGroup] = []
    for _, facts in sorted(grouped.items(), key=lambda item: _period_context_group_sort_key(item[1]), reverse=True):
        context_facts = tuple(sorted(facts, key=lambda fact: (fact.taxonomy.lower(), fact.concept.lower(), fact.raw_fact_id)))
        if not context_facts:
            continue
        statement_relationship_by_key = {
            key: _statement_relationship_for_facts(target=target, facts=concept_facts)
            for key, concept_facts in _facts_grouped_by_key(context_facts).items()
        }
        prompt_fact_pool = _prompt_fact_pool_for_context(
            facts=context_facts,
            statement_relationship_by_key=statement_relationship_by_key,
        )
        if not prompt_fact_pool:
            continue
        period_context = _period_context_payload(context_facts)
        period_groups.append(
            _FormulaProposalPeriodGroup(
                facts=context_facts,
                period_context=period_context,
                prompt_fact_pool=prompt_fact_pool,
                statement_relationship_by_key=statement_relationship_by_key,
            )
        )

    grouped_by_concept_pool: dict[tuple[object, ...], list[_FormulaProposalPeriodGroup]] = {}
    for group in period_groups:
        pool_key = _concept_pool_context_key(target=target, period_group=group)
        grouped_by_concept_pool.setdefault(pool_key, []).append(group)

    contexts: list[FormulaProposalContext] = []
    for concept_pool_groups in grouped_by_concept_pool.values():
        representative = concept_pool_groups[0]
        period_context = _merged_period_context_payload(concept_pool_groups)
        base_fingerprint_payload = _base_context_fingerprint_payload(
            target=target,
            facts=representative.facts,
            prompt_fact_pool=representative.prompt_fact_pool,
        )
        context_id_payload = {
            "target_metric_name": target.target_metric_name,
            "target_xbrl_concept": target.target_xbrl_concept,
            "context": base_fingerprint_payload,
        }
        contexts.append(
            FormulaProposalContext(
                context_id=_stable_hash(context_id_payload)[:12],
                target_primary_statement=target.statement_type.strip() or "unknown_statement",
                period_context=period_context,
                facts=representative.facts,
                prompt_fact_pool=representative.prompt_fact_pool,
                statement_relationship_by_key=representative.statement_relationship_by_key,
                base_fingerprint_payload=base_fingerprint_payload,
            )
        )
    return tuple(contexts)


def formula_context_fingerprint(
    *,
    target: FormulaProposalTarget,
    context: FormulaProposalContext,
    provider_name: str,
    model_name: str,
) -> tuple[str, dict[str, object]]:
    """Return the exact reusable identity for one provider/context request."""
    payload = {
        "cache_schema_version": FORMULA_PROPOSAL_CACHE_SCHEMA_VERSION,
        "fingerprint_version": FORMULA_CONTEXT_FINGERPRINT_VERSION,
        "prompt_version": FORMULA_PROPOSAL_PROMPT_VERSION,
        "statement_bucket_classifier_version": STATEMENT_BUCKET_CLASSIFIER_VERSION,
        "target_catalog_version": TARGET_CATALOG_VERSION,
        "provider_name": provider_name,
        "model_name": model_name,
        "target_metric_name": target.target_metric_name,
        "target_xbrl_concept": target.target_xbrl_concept,
        "target_primary_statement": context.target_primary_statement,
        "context": context.base_fingerprint_payload,
    }
    return _stable_hash(payload), payload


def _target_unit_compatible_facts(
    *,
    target: FormulaProposalTarget,
    facts: tuple[FormulaProposalFact, ...],
) -> tuple[FormulaProposalFact, ...]:
    unit_family = _target_unit_family(target)
    if unit_family == _UNIT_FAMILY_PER_SHARE:
        return tuple(fact for fact in facts if _is_per_share_unit(fact.unit))
    if unit_family == _UNIT_FAMILY_SHARES:
        return tuple(fact for fact in facts if _is_share_unit(fact.unit))
    if unit_family == _UNIT_FAMILY_MONETARY:
        return tuple(fact for fact in facts if _is_monetary_unit(fact.unit))
    return ()


def _target_unit_family(target: FormulaProposalTarget) -> str:
    concept = _normalize_key_part(target.concept)
    metric_name = _normalize_key_part(target.target_metric_name)
    statement_type = _normalize_key_part(target.statement_type)
    if "earningspershare" in concept or metric_name.endswith("eps") or "_eps" in metric_name:
        return _UNIT_FAMILY_PER_SHARE
    if "shares" in concept or "share" in statement_type or "shares" in metric_name:
        return _UNIT_FAMILY_SHARES
    if statement_type in _MONETARY_STATEMENT_TYPES:
        return _UNIT_FAMILY_MONETARY
    return ""


def _is_per_share_unit(unit: str) -> bool:
    normalized = unit.strip().lower()
    return "/" in normalized and "share" in normalized


def _is_share_unit(unit: str) -> bool:
    return unit.strip().lower() in {"share", "shares"}


def _is_monetary_unit(unit: str) -> bool:
    normalized = unit.strip().upper()
    if "/" in normalized:
        return False
    return normalized in _COMMON_CURRENCY_UNITS


def formula_context_prompt_payload(
    *,
    context: FormulaProposalContext,
    formula_context_hash: str,
) -> dict[str, object]:
    """Return the non-secret context metadata included in the model prompt."""
    return {
        "context_id": context.context_id,
        "formula_context_hash": formula_context_hash,
        "target_primary_statement": context.target_primary_statement,
        "period_context": context.period_context,
        "statement_bucket_counts": _statement_bucket_counts(context.prompt_fact_pool),
        "statement_policy": {
            "first": "Try same_statement facts for the target's primary statement.",
            "second": "Use unclassified_same_period facts only when same_statement facts are insufficient.",
            "fallback": (
                "Use cross_statement facts only when no credible same-statement formula exists; "
                "explain the accounting reason in the component role or reason."
            ),
        },
    }


def load_formula_proposal_cache(
    *,
    cache_dir: Path,
    formula_context_hash: str,
    target: FormulaProposalTarget,
    provider_name: str,
    model_name: str,
) -> tuple[FormulaProposalProviderResult | None, str]:
    """Load a cached structured provider result for an identical context."""
    cache_path = formula_proposal_cache_path(cache_dir=cache_dir, formula_context_hash=formula_context_hash)
    if not cache_path.exists():
        return None, ""
    try:
        entry = json.loads(cache_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"cache read failed: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"cache JSON invalid: {exc}"

    if entry.get("cache_schema_version") != FORMULA_PROPOSAL_CACHE_SCHEMA_VERSION:
        return None, "cache schema version mismatch"
    if entry.get("prompt_version") != FORMULA_PROPOSAL_PROMPT_VERSION:
        return None, "cache prompt version mismatch"
    try:
        response = FormulaProposalResponse.model_validate(entry.get("response"))
    except ValueError as exc:
        return None, f"cache response invalid: {exc}"
    return (
        provider_result_from_response(
            provider_name=provider_name,
            model_name=model_name,
            target=target,
            response=response,
        ),
        "",
    )


def save_formula_proposal_cache(
    *,
    cache_dir: Path,
    formula_context_hash: str,
    fingerprint_payload: dict[str, object],
    result: FormulaProposalProviderResult,
) -> str:
    """Persist successful structured provider decisions for exact reuse."""
    if result.provider_status not in {PROVIDER_STATUS_PROPOSED, PROVIDER_STATUS_TARGET_ZERO, PROVIDER_STATUS_NO_FORMULA}:
        return ""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = formula_proposal_cache_path(cache_dir=cache_dir, formula_context_hash=formula_context_hash)
    entry = {
        "cache_schema_version": FORMULA_PROPOSAL_CACHE_SCHEMA_VERSION,
        "prompt_version": FORMULA_PROPOSAL_PROMPT_VERSION,
        "formula_context_hash": formula_context_hash,
        "fingerprint_payload": fingerprint_payload,
        "provider_status": result.provider_status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "response": _response_from_provider_result(result).model_dump(mode="json"),
    }
    tmp_path = cache_path.with_name(f"{cache_path.name}.{os.getpid()}.tmp")
    try:
        tmp_path.write_text(json.dumps(entry, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(cache_path)
    except OSError as exc:
        return f"cache write failed: {exc}"
    return ""


def formula_proposal_cache_path(*, cache_dir: Path, formula_context_hash: str) -> Path:
    """Return the cache file path for one formula context hash."""
    return cache_dir / f"{formula_context_hash}.json"


def validate_formula_proposal(
    *,
    target: FormulaProposalTarget,
    proposal: FormulaProposalProviderResult,
    fact_pool: tuple[FormulaProposalFact, ...],
    statement_relationship_by_key: dict[tuple[str, str], str] | None = None,
) -> FormulaProposalValidationResult:
    """Validate that a model proposal only uses compatible available raw facts."""
    if proposal.provider_status in {PROVIDER_STATUS_UNAVAILABLE, PROVIDER_STATUS_FAILED}:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_NOT_APPLICABLE,
            skip_reason=proposal.provider_status,
            valid_component_count=0,
            notes=proposal.error,
        )
    if proposal.provider_status == PROVIDER_STATUS_TARGET_ZERO or proposal.target_is_zero:
        return _validate_zero_target_proposal(
            target=target,
            proposal=proposal,
            fact_pool=fact_pool,
            statement_relationship_by_key=statement_relationship_by_key,
        )
    if proposal.no_formula:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_NOT_APPLICABLE,
            skip_reason=PROVIDER_STATUS_NO_FORMULA,
            valid_component_count=0,
            notes=proposal.reason,
        )
    if not proposal.components:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_NO_COMPONENTS,
            valid_component_count=0,
            notes="Provider returned a formula without components.",
        )

    facts_by_key: dict[tuple[str, str], tuple[FormulaProposalFact, ...]] = {}
    for fact in fact_pool:
        facts_by_key.setdefault(fact.concept_key, ())
        facts_by_key[fact.concept_key] = (*facts_by_key[fact.concept_key], fact)

    invalid_components: list[str] = []
    circular_components: list[str] = []
    missing_value_components: list[str] = []
    cross_statement_without_explanation: list[str] = []
    matched_facts: list[FormulaProposalFact] = []
    component_period_keys: list[Counter[tuple[str, str, int | None, str]]] = []

    for component in proposal.components:
        component_key = (_normalize_key_part(component.taxonomy), _normalize_key_part(component.concept))
        component_label = f"{component.taxonomy}:{component.concept}"
        if component_key == target.concept_key:
            circular_components.append(component_label)
            continue
        component_facts = facts_by_key.get(component_key, ())
        if not component_facts:
            invalid_components.append(component_label)
            continue
        if (
            statement_relationship_by_key
            and statement_relationship_by_key.get(component_key) == STATEMENT_RELATIONSHIP_CROSS
            and not _has_cross_statement_explanation(component)
        ):
            cross_statement_without_explanation.append(component_label)
            continue
        numeric_facts = tuple(fact for fact in component_facts if fact.value_numeric is not None)
        if not numeric_facts:
            missing_value_components.append(component_label)
            continue
        matched_facts.extend(numeric_facts)
        component_period_keys.append(
            Counter(
                fact.period_unit_key
                for fact in numeric_facts
                if fact.unit and fact.period_type and fact.fiscal_year is not None and fact.fiscal_period
            )
        )

    if invalid_components:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_OUTSIDE_FACT_POOL,
            valid_component_count=len(component_period_keys),
            invalid_components=tuple(sorted(set(invalid_components))),
            circular_components=tuple(sorted(set(circular_components))),
            notes="One or more components were not present in the eligible raw fact pool.",
        )
    if circular_components:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_CIRCULAR_COMPONENT,
            valid_component_count=len(component_period_keys),
            circular_components=tuple(sorted(set(circular_components))),
            notes="The missing target itself was used as a component.",
        )
    if cross_statement_without_explanation:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_CROSS_STATEMENT_EXPLANATION,
            valid_component_count=len(component_period_keys),
            invalid_components=tuple(sorted(set(cross_statement_without_explanation))),
            notes="One or more cross-statement components did not explain why a same-statement formula was insufficient.",
        )
    if missing_value_components:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_NO_NUMERIC_VALUES,
            valid_component_count=len(component_period_keys),
            invalid_components=tuple(sorted(set(missing_value_components))),
            notes="One or more components had no numeric values.",
        )
    if not component_period_keys:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_NO_COMPONENTS,
            valid_component_count=0,
            notes="No components had enough period/unit evidence to validate.",
        )

    common_keys = set(component_period_keys[0])
    for keys in component_period_keys[1:]:
        common_keys &= set(keys)
    if not common_keys:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_NO_COMMON_PERIOD_UNIT,
            valid_component_count=len(component_period_keys),
            matched_raw_fact_ids=_raw_fact_ids(matched_facts),
            matched_accession_numbers=_accessions(matched_facts),
            notes="Components do not share a common unit, period type, fiscal year, and fiscal period.",
        )

    clean_common_keys = tuple(
        key
        for key in sorted(common_keys, key=_period_unit_sort_key)
        if all(counter[key] == 1 for counter in component_period_keys)
    )
    if not clean_common_keys:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_DUPLICATE_FACTS,
            valid_component_count=len(component_period_keys),
            matched_raw_fact_ids=_raw_fact_ids(matched_facts),
            matched_accession_numbers=_accessions(matched_facts),
            common_period_units=_format_period_unit_keys(common_keys),
            notes="Common period/unit evidence exists, but duplicate same-period component facts block validation.",
        )

    return FormulaProposalValidationResult(
        validation_status=VALIDATION_STATUS_VALIDATED,
        skip_reason="",
        valid_component_count=len(component_period_keys),
        matched_raw_fact_ids=_raw_fact_ids(matched_facts),
        matched_accession_numbers=_accessions(matched_facts),
        common_period_units=_format_period_unit_keys(clean_common_keys),
        notes="All components are in the raw fact pool and share at least one unambiguous period/unit.",
    )


def _validate_zero_target_proposal(
    *,
    target: FormulaProposalTarget,
    proposal: FormulaProposalProviderResult,
    fact_pool: tuple[FormulaProposalFact, ...],
    statement_relationship_by_key: dict[tuple[str, str], str] | None,
) -> FormulaProposalValidationResult:
    """Validate that a zero-target decision cites available same-period evidence."""
    if not proposal.components:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_ZERO_TARGET_NO_EVIDENCE,
            valid_component_count=0,
            notes="Provider proposed target zero without referencing supporting raw facts.",
        )

    facts_by_key: dict[tuple[str, str], tuple[FormulaProposalFact, ...]] = {}
    for fact in fact_pool:
        facts_by_key.setdefault(fact.concept_key, ())
        facts_by_key[fact.concept_key] = (*facts_by_key[fact.concept_key], fact)

    invalid_components: list[str] = []
    circular_components: list[str] = []
    missing_value_components: list[str] = []
    cross_statement_without_explanation: list[str] = []
    matched_facts: list[FormulaProposalFact] = []
    matched_component_keys: set[tuple[str, str]] = set()

    for component in proposal.components:
        component_key = (_normalize_key_part(component.taxonomy), _normalize_key_part(component.concept))
        component_label = f"{component.taxonomy}:{component.concept}"
        if component_key == target.concept_key:
            circular_components.append(component_label)
            continue
        component_facts = facts_by_key.get(component_key, ())
        if not component_facts:
            invalid_components.append(component_label)
            continue
        if (
            statement_relationship_by_key
            and statement_relationship_by_key.get(component_key) == STATEMENT_RELATIONSHIP_CROSS
            and not _has_cross_statement_explanation(component)
        ):
            cross_statement_without_explanation.append(component_label)
            continue
        numeric_facts = tuple(fact for fact in component_facts if fact.value_numeric is not None)
        if not numeric_facts:
            missing_value_components.append(component_label)
            continue
        matched_component_keys.add(component_key)
        matched_facts.extend(numeric_facts)

    if invalid_components:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_OUTSIDE_FACT_POOL,
            valid_component_count=len(matched_component_keys),
            invalid_components=tuple(sorted(set(invalid_components))),
            circular_components=tuple(sorted(set(circular_components))),
            notes="One or more zero-evidence facts were not present in the eligible raw fact pool.",
        )
    if circular_components:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_CIRCULAR_COMPONENT,
            valid_component_count=len(matched_component_keys),
            circular_components=tuple(sorted(set(circular_components))),
            notes="The missing target itself was cited as zero-evidence.",
        )
    if cross_statement_without_explanation:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_CROSS_STATEMENT_EXPLANATION,
            valid_component_count=len(matched_component_keys),
            invalid_components=tuple(sorted(set(cross_statement_without_explanation))),
            notes="One or more cross-statement zero-evidence facts did not explain the accounting connection.",
        )
    if missing_value_components:
        return FormulaProposalValidationResult(
            validation_status=VALIDATION_STATUS_FAILED,
            skip_reason=VALIDATION_SKIP_NO_NUMERIC_VALUES,
            valid_component_count=len(matched_component_keys),
            invalid_components=tuple(sorted(set(missing_value_components))),
            notes="One or more zero-evidence facts had no numeric values.",
        )

    period_unit_keys = {
        fact.period_unit_key
        for fact in matched_facts
        if fact.unit and fact.period_type and fact.fiscal_year is not None and fact.fiscal_period
    }
    return FormulaProposalValidationResult(
        validation_status=VALIDATION_STATUS_ZERO_EVIDENCE,
        skip_reason="",
        valid_component_count=len(matched_component_keys),
        matched_raw_fact_ids=_raw_fact_ids(matched_facts),
        matched_accession_numbers=_accessions(matched_facts),
        common_period_units=_format_period_unit_keys(period_unit_keys),
        notes=(
            "Supporting zero-evidence facts are in the eligible raw fact pool; "
            "review before treating the missing target as zero."
        ),
    )


def consensus_label(
    proposals: tuple[FormulaProposalProviderResult, ...],
    validations: tuple[FormulaProposalValidationResult, ...],
) -> str:
    """Return a target-level agreement label for report display."""
    signatures: Counter[tuple[tuple[str, str, str], ...]] = Counter()
    validated_count = 0
    zero_validated_count = 0
    has_formula_attempt = False
    has_zero_attempt = False
    for proposal, validation in zip(proposals, validations, strict=False):
        if proposal.provider_status == PROVIDER_STATUS_TARGET_ZERO:
            has_zero_attempt = True
            if validation.validation_status == VALIDATION_STATUS_ZERO_EVIDENCE:
                zero_validated_count += 1
            continue
        if proposal.provider_status != PROVIDER_STATUS_PROPOSED:
            continue
        has_formula_attempt = True
        if validation.validation_status != VALIDATION_STATUS_VALIDATED:
            continue
        validated_count += 1
        signatures[_component_signature(proposal)] += 1
    if any(count >= 2 for count in signatures.values()):
        return CONSENSUS_VALIDATED
    if zero_validated_count >= 2:
        return CONSENSUS_TARGET_ZERO
    if validated_count == 1 and zero_validated_count == 0 and not has_zero_attempt:
        return CONSENSUS_SINGLE_VALIDATED
    if validated_count == 0 and zero_validated_count == 1 and not has_formula_attempt:
        return CONSENSUS_SINGLE_TARGET_ZERO
    if validated_count or zero_validated_count or has_formula_attempt or has_zero_attempt:
        return CONSENSUS_DISAGREEMENT
    return CONSENSUS_NOT_APPLICABLE


def _preferred_period_type_for_statement(statement_type: str) -> str:
    clean = _normalize_key_part(statement_type)
    if clean == "balance_sheet":
        return "instant"
    if clean in {"income_statement", "cash_flow_statement"}:
        return "duration"
    return ""


def _facts_grouped_by_key(
    facts: tuple[FormulaProposalFact, ...],
) -> dict[tuple[str, str], tuple[FormulaProposalFact, ...]]:
    grouped: dict[tuple[str, str], tuple[FormulaProposalFact, ...]] = {}
    for fact in facts:
        grouped.setdefault(fact.concept_key, ())
        grouped[fact.concept_key] = (*grouped[fact.concept_key], fact)
    return grouped


def _statement_relationship_for_facts(
    *,
    target: FormulaProposalTarget,
    facts: tuple[FormulaProposalFact, ...],
) -> str:
    relationships = {_statement_relationship(target=target, fact=fact) for fact in facts}
    if STATEMENT_RELATIONSHIP_SAME in relationships:
        return STATEMENT_RELATIONSHIP_SAME
    if STATEMENT_RELATIONSHIP_CROSS in relationships:
        return STATEMENT_RELATIONSHIP_CROSS
    return STATEMENT_RELATIONSHIP_UNCLASSIFIED


def _statement_relationship(
    *,
    target: FormulaProposalTarget,
    fact: FormulaProposalFact,
) -> str:
    target_statement = _normalize_key_part(target.statement_type)
    mapped_statement = _normalize_key_part(fact.mapped_statement_type)
    if not target_statement or not mapped_statement:
        return STATEMENT_RELATIONSHIP_UNCLASSIFIED
    if target_statement == mapped_statement:
        return STATEMENT_RELATIONSHIP_SAME
    return STATEMENT_RELATIONSHIP_CROSS


def _prompt_fact_pool_for_context(
    *,
    facts: tuple[FormulaProposalFact, ...],
    statement_relationship_by_key: dict[tuple[str, str], str],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for (taxonomy_key, concept_key), concept_facts in sorted(_facts_grouped_by_key(facts).items()):
        sample = concept_facts[0]
        rows.append(
            {
                "taxonomy": sample.taxonomy,
                "concept": sample.concept,
                "label": next((fact.label for fact in concept_facts if fact.label), ""),
                "statement_relationship": statement_relationship_by_key.get(
                    (taxonomy_key, concept_key),
                    STATEMENT_RELATIONSHIP_UNCLASSIFIED,
                ),
                "mapping_statuses": _sorted_text_values(fact.mapping_status for fact in concept_facts),
                "mapped_metric_names": _sorted_text_values(fact.mapped_metric_name for fact in concept_facts),
                "mapped_statement_types": _sorted_text_values(fact.mapped_statement_type for fact in concept_facts),
                "fact_rows": len(concept_facts),
                "units": _sorted_text_values(fact.unit for fact in concept_facts),
                "period_types": _sorted_text_values(fact.period_type for fact in concept_facts),
                "forms": _sorted_text_values(fact.form for fact in concept_facts),
                "sample_raw_fact_ids": tuple(fact.raw_fact_id for fact in concept_facts[:5]),
                "sample_accessions": tuple(dict.fromkeys(fact.accession_number for fact in concept_facts if fact.accession_number))[:3],
            }
        )
    relationship_order = {
        STATEMENT_RELATIONSHIP_SAME: 0,
        STATEMENT_RELATIONSHIP_UNCLASSIFIED: 1,
        STATEMENT_RELATIONSHIP_CROSS: 2,
    }
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                relationship_order.get(str(row.get("statement_relationship") or ""), 9),
                str(row.get("taxonomy") or "").lower(),
                str(row.get("concept") or "").lower(),
            ),
        )
    )


def _period_context_payload(facts: tuple[FormulaProposalFact, ...]) -> dict[str, object]:
    sample = facts[0]
    return {
        "accession_numbers": tuple(dict.fromkeys(fact.accession_number for fact in facts if fact.accession_number)),
        "forms": _sorted_text_values(fact.form for fact in facts),
        "unit": sample.unit,
        "period_type": sample.period_type,
        "fiscal_year": sample.fiscal_year,
        "fiscal_period": sample.fiscal_period or "",
        "start_date": sample.start_date.isoformat() if sample.start_date else "",
        "end_date": sample.end_date.isoformat() if sample.end_date else "",
        "filed_dates": _sorted_text_values(fact.filed_date.isoformat() if fact.filed_date else "" for fact in facts),
        "raw_fact_rows": len(facts),
    }


def _concept_pool_context_key(
    *,
    target: FormulaProposalTarget,
    period_group: _FormulaProposalPeriodGroup,
) -> tuple[object, ...]:
    sample = period_group.facts[0]
    return (
        _normalize_key_part(target.target_metric_name),
        _normalize_key_part(target.target_xbrl_concept),
        _normalize_key_part(target.statement_type),
        sample.unit.strip(),
        _normalize_key_part(sample.period_type),
        _sorted_text_values(fact.form for fact in period_group.facts),
        tuple(_concept_pool_row_key(row) for row in period_group.prompt_fact_pool),
    )


def _concept_pool_row_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        _normalize_key_part(str(row.get("taxonomy") or "")),
        _normalize_key_part(str(row.get("concept") or "")),
        str(row.get("statement_relationship") or ""),
        tuple(row.get("mapping_statuses") or ()),
        tuple(row.get("mapped_metric_names") or ()),
        tuple(row.get("mapped_statement_types") or ()),
    )


def _merged_period_context_payload(groups: list[_FormulaProposalPeriodGroup]) -> dict[str, object]:
    representative = groups[0].period_context
    context = dict(representative)
    period_contexts = tuple(group.period_context for group in groups)
    context["accession_numbers"] = _sorted_text_values(
        accession
        for period_context in period_contexts
        for accession in period_context.get("accession_numbers", ())
    )
    context["forms"] = _sorted_text_values(
        form
        for period_context in period_contexts
        for form in period_context.get("forms", ())
    )
    context["filed_dates"] = _sorted_text_values(
        filed_date
        for period_context in period_contexts
        for filed_date in period_context.get("filed_dates", ())
    )
    context["raw_fact_rows"] = sum(int(period_context.get("raw_fact_rows") or 0) for period_context in period_contexts)
    context["period_coverage"] = _period_coverage_label(period_contexts)
    context["period_contexts"] = tuple(_compact_period_context(period_context) for period_context in period_contexts)
    if len(period_contexts) > 1:
        for field in ("fiscal_year", "fiscal_period", "start_date", "end_date"):
            values = {str(period_context.get(field) or "") for period_context in period_contexts}
            if len(values) > 1:
                context[field] = ""
    return context


def _compact_period_context(period_context: dict[str, object]) -> dict[str, object]:
    return {
        "forms": tuple(period_context.get("forms") or ()),
        "fiscal_year": period_context.get("fiscal_year"),
        "fiscal_period": period_context.get("fiscal_period") or "",
        "start_date": period_context.get("start_date") or "",
        "end_date": period_context.get("end_date") or "",
        "accession_numbers": tuple(period_context.get("accession_numbers") or ()),
    }


def _period_coverage_label(period_contexts: tuple[dict[str, object], ...]) -> str:
    labels_by_form: dict[str, list[str]] = {}
    for period_context in period_contexts:
        label = _period_context_label(period_context)
        if not label:
            continue
        forms = tuple(period_context.get("forms") or ()) or ("unknown form",)
        for form in forms:
            labels_by_form.setdefault(str(form), [])
            if label not in labels_by_form[str(form)]:
                labels_by_form[str(form)].append(label)
    return "; ".join(
        f"{form} periods: {', '.join(labels)}"
        for form, labels in sorted(labels_by_form.items())
    )


def _period_context_label(period_context: dict[str, object]) -> str:
    fiscal_year = period_context.get("fiscal_year")
    fiscal_period = str(period_context.get("fiscal_period") or "").strip().upper()
    if fiscal_year is not None and fiscal_period:
        return f"{fiscal_year} {fiscal_period}"
    end_date = str(period_context.get("end_date") or "").strip()
    if end_date:
        return end_date
    accessions = tuple(period_context.get("accession_numbers") or ())
    if accessions:
        return str(accessions[0])
    return ""


def _base_context_fingerprint_payload(
    *,
    target: FormulaProposalTarget,
    facts: tuple[FormulaProposalFact, ...],
    prompt_fact_pool: tuple[dict[str, object], ...],
) -> dict[str, object]:
    sample = facts[0]
    concepts = [
        {
            "taxonomy": row.get("taxonomy") or "",
            "concept": row.get("concept") or "",
            "label": row.get("label") or "",
            "statement_relationship": row.get("statement_relationship") or "",
            "mapping_statuses": row.get("mapping_statuses") or (),
            "mapped_metric_names": row.get("mapped_metric_names") or (),
            "mapped_statement_types": row.get("mapped_statement_types") or (),
        }
        for row in prompt_fact_pool
    ]
    return {
        "target_metric_name": target.target_metric_name,
        "target_xbrl_concept": target.target_xbrl_concept,
        "target_primary_statement": target.statement_type,
        "unit": sample.unit,
        "period_type": sample.period_type,
        "forms": _sorted_text_values(fact.form for fact in facts),
        "statement_bucket_counts": _statement_bucket_counts(prompt_fact_pool),
        "concepts": concepts,
    }


def _statement_bucket_counts(rows: tuple[dict[str, object], ...]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[str(row.get("statement_relationship") or STATEMENT_RELATIONSHIP_UNCLASSIFIED)] += 1
    return dict(sorted(counts.items()))


def _period_context_group_sort_key(facts: list[FormulaProposalFact]) -> tuple[int, int, str, str]:
    sample = facts[0]
    return (
        sample.fiscal_year or 0,
        _fiscal_period_order(sample.fiscal_period),
        sample.end_date.isoformat() if sample.end_date else "",
        sample.accession_number,
    )


def _fiscal_period_order(value: str | None) -> int:
    clean = str(value or "").strip().upper()
    if clean == "FY":
        return 5
    if clean.startswith("Q") and clean[1:].isdigit():
        return int(clean[1:])
    return 0


def _sorted_text_values(values: Any) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _has_cross_statement_explanation(component: FormulaProposalComponentResponse) -> bool:
    return bool(component.role.strip() or component.reason.strip())


def _response_from_provider_result(result: FormulaProposalProviderResult) -> FormulaProposalResponse:
    return FormulaProposalResponse(
        no_formula=result.no_formula,
        target_is_zero=result.target_is_zero,
        target_metric_name=result.target_metric_name,
        target_xbrl_concept=result.target_xbrl_concept,
        formula_expression=result.formula_expression,
        components=list(result.components),
        confidence=result.confidence,
        reason=result.reason,
        uncertainty=result.uncertainty,
    )


def _stable_hash(payload: object) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _component_signature(proposal: FormulaProposalProviderResult) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (
                component.operator,
                _normalize_key_part(component.taxonomy),
                _normalize_key_part(component.concept),
            )
            for component in proposal.components
        )
    )


def _format_period_unit_keys(keys: set[tuple[str, str, int | None, str]] | tuple[tuple[str, str, int | None, str], ...]) -> tuple[str, ...]:
    return tuple(
        f"{fiscal_year or ''} {fiscal_period} {period_type} {unit}".strip()
        for unit, period_type, fiscal_year, fiscal_period in sorted(keys, key=_period_unit_sort_key)
    )


def _period_unit_sort_key(key: tuple[str, str, int | None, str]) -> tuple[int, str, str, str]:
    unit, period_type, fiscal_year, fiscal_period = key
    return (fiscal_year or 0, fiscal_period, period_type, unit)


def _raw_fact_ids(facts: list[FormulaProposalFact]) -> tuple[int, ...]:
    return tuple(sorted({fact.raw_fact_id for fact in facts}))


def _accessions(facts: list[FormulaProposalFact]) -> tuple[str, ...]:
    return tuple(sorted({fact.accession_number for fact in facts if fact.accession_number}))


def _normalize_key_part(value: str) -> str:
    return str(value or "").strip().lower()


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped
