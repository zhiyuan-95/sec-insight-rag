"""Structured historical records for three-judge semantic recommendations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_validator,
)

from src.processing.semantic_evidence import SemanticEvidencePacket

JUDGE_RESPONSE_COMPLETED = "completed"
JUDGE_RESPONSE_ABSTAINED = "abstained"
JUDGE_RESPONSE_TECHNICAL_FAILURE = "technical_failure"

RECOMMENDATION_UNANIMOUS_FORMULA = "unanimous_formula"
RECOMMENDATION_UNANIMOUS_ZERO = "unanimous_zero"
RECOMMENDATION_UNANIMOUS_ABSTENTION = "unanimous_abstention"
RECOMMENDATION_UNANIMOUS_MIXED = "unanimous_mixed"
RECOMMENDATION_NEEDS_REVIEW = "needs_review"
RECOMMENDATION_TECHNICAL_FAILURE = "technical_failure"


class SemanticFormulaComponentResponse(BaseModel):
    """One exact eligible concept and operator in a judge's formula."""

    model_config = ConfigDict(extra="forbid")

    taxonomy: str
    concept: str
    operator: Literal["+", "-"]
    evidence_refs: list[str]

    @field_validator("taxonomy", "concept")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean:
            raise ValueError("formula component identity must be non-empty")
        return clean

    @field_validator("evidence_refs")
    @classmethod
    def normalize_component_evidence(
        cls,
        value: list[str],
    ) -> list[str]:
        return _normalized_text_list(value)


class SemanticTargetRecommendationResponse(BaseModel):
    """One judge's structured decision for one missing system target."""

    model_config = ConfigDict(extra="forbid")

    target_metric_name: str
    statement_type: str
    decision: Literal["formula", "zero", "no_formula"]
    components: list[SemanticFormulaComponentResponse]
    evidence_refs: list[str]
    rationale: str

    @field_validator(
        "target_metric_name",
        "statement_type",
        "rationale",
    )
    @classmethod
    def strip_response_text(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean:
            raise ValueError("recommendation text fields must be non-empty")
        return clean

    @field_validator("evidence_refs")
    @classmethod
    def normalize_recommendation_evidence(
        cls,
        value: list[str],
    ) -> list[str]:
        return _normalized_text_list(value)

    @model_validator(mode="after")
    def validate_decision_shape(self) -> "SemanticTargetRecommendationResponse":
        if self.decision == "formula" and not self.components:
            raise ValueError("a formula decision requires components")
        if self.decision != "formula" and self.components:
            raise ValueError(
                "zero and no_formula decisions cannot contain components"
            )
        cited_evidence = {
            *self.evidence_refs,
            *(
                evidence_ref
                for component in self.components
                for evidence_ref in component.evidence_refs
            ),
        }
        if self.decision in {"formula", "zero"} and not cited_evidence:
            raise ValueError(
                "formula and zero decisions require packet evidence references"
            )
        return self


class SemanticJudgeBatchResponse(BaseModel):
    """One judge's decisions for every target in one semantic packet."""

    model_config = ConfigDict(extra="forbid")

    recommendations: list[SemanticTargetRecommendationResponse]


SEMANTIC_JUDGE_BATCH_RESPONSE_JSON_SCHEMA = (
    SemanticJudgeBatchResponse.model_json_schema()
)


@dataclass(frozen=True)
class SemanticJudgeIdentity:
    """One provider and model occupying a recommendation judge slot."""

    provider_name: str
    model_name: str


@dataclass(frozen=True)
class SemanticJudgeResponseRecord:
    """One judge's retained response or technical failure."""

    judge: SemanticJudgeIdentity
    response_status: str
    started_at: str
    completed_at: str
    response_json: str | None
    canonical_response_json: str | None
    error: str


@dataclass(frozen=True)
class SemanticTargetComparison:
    """Canonical three-way comparison for one missing target."""

    target_metric_name: str
    statement_type: str
    outcome: str
    judge_canonical_json: tuple[str | None, str | None, str | None]
    unanimous_canonical_json: str | None


@dataclass(frozen=True)
class SemanticRecommendationRecord:
    """Immutable historical record shared by all periods in one evidence group."""

    recommendation_request_id: str
    attempt_number: int
    company_id: str
    period_ids: tuple[str, ...]
    packet_content_sha256: str
    packet_json: str
    prompt_version: str
    judge_lineup: tuple[
        SemanticJudgeIdentity,
        SemanticJudgeIdentity,
        SemanticJudgeIdentity,
    ]
    judge_responses: tuple[
        SemanticJudgeResponseRecord,
        SemanticJudgeResponseRecord,
        SemanticJudgeResponseRecord,
    ]
    target_comparisons: tuple[SemanticTargetComparison, ...]
    outcome: str
    created_at: str


def normalize_semantic_judge_response(
    value: object,
    *,
    packet: SemanticEvidencePacket,
) -> tuple[SemanticJudgeBatchResponse, str]:
    """Validate one judge response and return its canonical comparison JSON."""
    response = _coerce_judge_response(value)
    expected_targets = {
        (target.metric_name, target.statement_type)
        for target in packet.targets
    }
    recommendations = {
        (
            recommendation.target_metric_name,
            recommendation.statement_type,
        ): recommendation
        for recommendation in response.recommendations
    }
    if len(recommendations) != len(response.recommendations):
        raise ValueError("semantic judge returned a duplicate target")
    if set(recommendations) != expected_targets:
        raise ValueError(
            "semantic judge targets did not exactly match the evidence packet"
        )

    eligible_concepts = {
        (concept.taxonomy.casefold(), concept.concept)
        for concept in packet.concepts
        if concept.component_eligible
    }
    evidence_ids = {
        concept.evidence_id for concept in packet.concepts
    } | {
        relationship.evidence_id for relationship in packet.relationships
    } | {
        assertion.assertion_id for assertion in packet.formula_assertions
    } | {
        validation.evidence_id for validation in packet.validations
    }
    canonical = []
    for target in packet.targets:
        recommendation = recommendations[
            (target.metric_name, target.statement_type)
        ]
        cited_evidence = {
            *recommendation.evidence_refs,
            *(
                evidence_ref
                for component in recommendation.components
                for evidence_ref in component.evidence_refs
            ),
        }
        unknown_evidence = cited_evidence - evidence_ids
        if unknown_evidence:
            raise ValueError(
                "semantic judge cited unknown evidence: "
                + ", ".join(sorted(unknown_evidence))
            )
        outside_pool = {
            f"{component.taxonomy}:{component.concept}"
            for component in recommendation.components
            if (
                component.taxonomy.casefold(),
                component.concept,
            )
            not in eligible_concepts
        }
        if outside_pool:
            raise ValueError(
                "semantic judge used ineligible formula components: "
                + ", ".join(sorted(outside_pool))
            )
        canonical.append(_canonical_target_decision(recommendation))
    canonical_json = _canonical_json({"recommendations": canonical})
    return response, canonical_json


def compare_semantic_judge_responses(
    *,
    packet: SemanticEvidencePacket,
    canonical_response_json: tuple[
        str | None,
        str | None,
        str | None,
    ],
) -> tuple[tuple[SemanticTargetComparison, ...], str]:
    """Compare three canonical judge responses for exact target unanimity."""
    parsed = tuple(
        (
            {
                (
                    item["target_metric_name"],
                    item["statement_type"],
                ): _canonical_json(item)
                for item in json.loads(value)["recommendations"]
            }
            if value is not None
            else None
        )
        for value in canonical_response_json
    )
    comparisons = []
    for target in packet.targets:
        key = (target.metric_name, target.statement_type)
        decisions = tuple(
            response.get(key) if response is not None else None
            for response in parsed
        )
        if any(decision is None for decision in decisions):
            outcome = RECOMMENDATION_TECHNICAL_FAILURE
            unanimous = None
        elif len(set(decisions)) != 1:
            outcome = RECOMMENDATION_NEEDS_REVIEW
            unanimous = None
        else:
            unanimous = decisions[0]
            decision = json.loads(unanimous)["decision"]
            outcome = {
                "formula": RECOMMENDATION_UNANIMOUS_FORMULA,
                "zero": RECOMMENDATION_UNANIMOUS_ZERO,
                "no_formula": RECOMMENDATION_UNANIMOUS_ABSTENTION,
            }[decision]
        comparisons.append(
            SemanticTargetComparison(
                target_metric_name=target.metric_name,
                statement_type=target.statement_type,
                outcome=outcome,
                judge_canonical_json=decisions,
                unanimous_canonical_json=unanimous,
            )
        )
    outcomes = {comparison.outcome for comparison in comparisons}
    if RECOMMENDATION_TECHNICAL_FAILURE in outcomes:
        group_outcome = RECOMMENDATION_TECHNICAL_FAILURE
    elif RECOMMENDATION_NEEDS_REVIEW in outcomes:
        group_outcome = RECOMMENDATION_NEEDS_REVIEW
    elif len(outcomes) == 1:
        group_outcome = next(iter(outcomes))
    else:
        group_outcome = RECOMMENDATION_UNANIMOUS_MIXED
    return tuple(comparisons), group_outcome


def semantic_recommendation_record_to_json(
    record: SemanticRecommendationRecord,
) -> str:
    """Serialize one recommendation record canonically for immutable storage."""
    return json.dumps(
        asdict(record),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def semantic_recommendation_record_from_json(
    value: str,
) -> SemanticRecommendationRecord:
    """Restore one recommendation record from its canonical stored JSON."""
    payload = json.loads(value)
    lineup = tuple(
        SemanticJudgeIdentity(**judge)
        for judge in payload["judge_lineup"]
    )
    responses = tuple(
        SemanticJudgeResponseRecord(
            judge=SemanticJudgeIdentity(**response["judge"]),
            response_status=response["response_status"],
            started_at=response["started_at"],
            completed_at=response["completed_at"],
            response_json=response["response_json"],
            canonical_response_json=response["canonical_response_json"],
            error=response["error"],
        )
        for response in payload["judge_responses"]
    )
    comparisons = tuple(
        SemanticTargetComparison(
            target_metric_name=comparison["target_metric_name"],
            statement_type=comparison["statement_type"],
            outcome=comparison["outcome"],
            judge_canonical_json=tuple(
                comparison["judge_canonical_json"]
            ),
            unanimous_canonical_json=(
                comparison["unanimous_canonical_json"]
            ),
        )
        for comparison in payload["target_comparisons"]
    )
    return SemanticRecommendationRecord(
        recommendation_request_id=payload["recommendation_request_id"],
        attempt_number=payload["attempt_number"],
        company_id=payload["company_id"],
        period_ids=tuple(payload["period_ids"]),
        packet_content_sha256=payload["packet_content_sha256"],
        packet_json=payload["packet_json"],
        prompt_version=payload["prompt_version"],
        judge_lineup=lineup,
        judge_responses=responses,
        target_comparisons=comparisons,
        outcome=payload["outcome"],
        created_at=payload["created_at"],
    )


def _coerce_judge_response(value: object) -> SemanticJudgeBatchResponse:
    if isinstance(value, SemanticJudgeBatchResponse):
        return value
    if isinstance(value, str):
        return SemanticJudgeBatchResponse.model_validate_json(value)
    return SemanticJudgeBatchResponse.model_validate(value)


def _canonical_target_decision(
    recommendation: SemanticTargetRecommendationResponse,
) -> dict[str, object]:
    return {
        "target_metric_name": recommendation.target_metric_name,
        "statement_type": recommendation.statement_type,
        "decision": recommendation.decision,
        "components": sorted(
            (
                {
                    "taxonomy": component.taxonomy.casefold(),
                    "concept": component.concept,
                    "operator": component.operator,
                    "evidence_refs": sorted(set(component.evidence_refs)),
                }
                for component in recommendation.components
            ),
            key=lambda item: (
                item["taxonomy"],
                item["concept"],
                item["operator"],
                item["evidence_refs"],
            ),
        ),
        "evidence_refs": sorted(set(recommendation.evidence_refs)),
    }


def _normalized_text_list(values: list[str]) -> list[str]:
    return sorted(
        {
            clean
            for value in values
            if (clean := str(value or "").strip())
        }
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
