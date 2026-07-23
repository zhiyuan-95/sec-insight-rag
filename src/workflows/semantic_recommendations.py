"""Thin orchestration for reusable three-judge semantic recommendations."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from src.analyze.prompts import (
    SEMANTIC_RECOMMENDATION_PROMPT_VERSION,
    build_semantic_recommendation_prompt,
)
from src.analyze.semantic_judges import (
    SemanticJudgeConfig,
    generate_semantic_judgment,
)
from src.processing.semantic_evidence import (
    SemanticEvidencePacket,
    SemanticRecommendationGroup,
)
from src.processing.semantic_recommendations import (
    JUDGE_RESPONSE_ABSTAINED,
    JUDGE_RESPONSE_COMPLETED,
    JUDGE_RESPONSE_TECHNICAL_FAILURE,
    RECOMMENDATION_TECHNICAL_FAILURE,
    SemanticJudgeIdentity,
    SemanticJudgeResponseRecord,
    SemanticRecommendationRecord,
    compare_semantic_judge_responses,
    normalize_semantic_judge_response,
)
from src.storage.semantic_recommendations_repository import (
    SemanticRecommendationConflictError,
    SemanticRecommendationRepository,
)

SemanticJudgeCaller = Callable[[str, SemanticJudgeConfig], object]


def record_semantic_recommendation_group(
    *,
    group: SemanticRecommendationGroup,
    judges: Sequence[SemanticJudgeConfig],
    repository: SemanticRecommendationRepository,
    call_judge: SemanticJudgeCaller = generate_semantic_judgment,
    retry_technical_failure: bool = False,
) -> SemanticRecommendationRecord:
    """Reuse or record one blind, concurrent, three-judge recommendation.

    Technical failures are reused by default. Callers must explicitly request
    a new immutable attempt when retrying the unchanged group.
    """
    lineup = _validated_lineup(group, judges)
    if not group.packet.targets:
        raise ValueError(
            "semantic recommendation group requires a missing target"
        )
    existing = repository.get(group.recommendation_request_id)
    if existing is not None and not (
        retry_technical_failure
        and existing.outcome == RECOMMENDATION_TECHNICAL_FAILURE
    ):
        return existing
    attempt_number = (
        existing.attempt_number + 1 if existing is not None else 1
    )

    prompt = build_semantic_recommendation_prompt(
        company_id=group.company_id,
        recommendation_request_id=group.recommendation_request_id,
        packet_json=group.packet.to_json(),
    )
    responses: list[SemanticJudgeResponseRecord | None] = [None, None, None]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                _call_and_record_judge,
                prompt=prompt,
                judge=judge,
                packet=group.packet,
                call_judge=call_judge,
            ): index
            for index, judge in enumerate(judges)
        }
        for future in as_completed(futures):
            responses[futures[future]] = future.result()

    judge_responses = tuple(
        response for response in responses if response is not None
    )
    if len(judge_responses) != 3:
        raise RuntimeError("three semantic judge records were not produced")
    canonical = tuple(
        response.canonical_response_json
        for response in judge_responses
    )
    comparisons, outcome = compare_semantic_judge_responses(
        packet=group.packet,
        canonical_response_json=canonical,
    )
    record = SemanticRecommendationRecord(
        recommendation_request_id=group.recommendation_request_id,
        attempt_number=attempt_number,
        company_id=group.company_id,
        period_ids=group.period_ids,
        packet_content_sha256=group.packet.content_sha256,
        packet_json=group.packet.to_json(),
        prompt_version=SEMANTIC_RECOMMENDATION_PROMPT_VERSION,
        judge_lineup=lineup,
        judge_responses=judge_responses,
        target_comparisons=comparisons,
        outcome=outcome,
        created_at=_utc_now(),
    )
    try:
        repository.insert(record)
    except SemanticRecommendationConflictError:
        concurrent = repository.get_attempt(
            group.recommendation_request_id,
            attempt_number,
        )
        if concurrent is None:
            raise
        return concurrent
    return record


def _call_and_record_judge(
    *,
    prompt: str,
    judge: SemanticJudgeConfig,
    packet: SemanticEvidencePacket,
    call_judge: SemanticJudgeCaller,
) -> SemanticJudgeResponseRecord:
    identity = SemanticJudgeIdentity(
        provider_name=judge.provider_name,
        model_name=judge.model_name,
    )
    started_at = _utc_now()
    try:
        response, canonical_json = normalize_semantic_judge_response(
            call_judge(prompt, judge),
            packet=packet,
        )
        response_status = (
            JUDGE_RESPONSE_ABSTAINED
            if all(
                recommendation.decision == "no_formula"
                for recommendation in response.recommendations
            )
            else JUDGE_RESPONSE_COMPLETED
        )
        response_json = response.model_dump_json()
        error = ""
    except Exception as exc:
        response_status = JUDGE_RESPONSE_TECHNICAL_FAILURE
        response_json = None
        canonical_json = None
        error = f"{type(exc).__name__}: {exc}"
    return SemanticJudgeResponseRecord(
        judge=identity,
        response_status=response_status,
        started_at=started_at,
        completed_at=_utc_now(),
        response_json=response_json,
        canonical_response_json=canonical_json,
        error=error,
    )


def _validated_lineup(
    group: SemanticRecommendationGroup,
    judges: Sequence[SemanticJudgeConfig],
) -> tuple[
    SemanticJudgeIdentity,
    SemanticJudgeIdentity,
    SemanticJudgeIdentity,
]:
    if len(judges) != 3:
        raise ValueError("exactly three semantic judges are required")
    identities = tuple(
        SemanticJudgeIdentity(
            provider_name=judge.provider_name.strip(),
            model_name=judge.model_name.strip(),
        )
        for judge in judges
    )
    if any(
        not identity.provider_name or not identity.model_name
        for identity in identities
    ):
        raise ValueError("semantic judge provider and model must be non-empty")
    if len({identity.model_name for identity in identities}) != 3:
        raise ValueError("semantic judge models must be distinct")
    if {identity.model_name for identity in identities} != set(
        group.judge_models
    ):
        raise ValueError(
            "configured semantic judges do not match the evidence group"
        )
    return identities


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
