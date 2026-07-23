from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src.analyze.semantic_judges import SemanticJudgeConfig
from src.processing.semantic_evidence import (
    SemanticConceptEvidence,
    SemanticEvidencePacket,
    SemanticRecommendationGroup,
    SemanticTargetDefinition,
)
from src.processing.semantic_recommendations import (
    SemanticFormulaComponentResponse,
    SemanticJudgeBatchResponse,
    SemanticTargetRecommendationResponse,
)
from src.storage import (
    SemanticRecommendationConflictError,
    SemanticRecommendationRepository,
    connect_sqlite,
)
from src.workflows.semantic_recommendations import (
    record_semantic_recommendation_group,
)


def test_new_group_calls_three_blind_judges_concurrently_and_records_unanimity(
    tmp_path: Path,
) -> None:
    group = _group()
    judges = _judges()
    barrier = threading.Barrier(3)
    lock = threading.Lock()
    prompts: list[str] = []
    calls: list[str] = []

    def call_judge(
        prompt: str,
        judge: SemanticJudgeConfig,
    ) -> SemanticJudgeBatchResponse:
        with lock:
            prompts.append(prompt)
            calls.append(judge.model_name)
        barrier.wait(timeout=2)
        return _formula_response()

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        record = record_semantic_recommendation_group(
            group=group,
            judges=judges,
            repository=repository,
            call_judge=call_judge,
        )

        assert sorted(calls) == sorted(judge.model_name for judge in judges)
        assert len(set(prompts)) == 1
        assert group.packet.content_sha256 in prompts[0]
        assert "FY-2024" not in prompts[0]
        assert record.outcome == "unanimous_formula"
        assert record.target_comparisons[0].outcome == "unanimous_formula"
        assert record.packet_json == group.packet.to_json()
        assert tuple(
            response.judge for response in record.judge_responses
        ) == record.judge_lineup
        assert len(record.target_comparisons[0].judge_canonical_json) == 3
        assert all(
            response.response_status == "completed"
            for response in record.judge_responses
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM financial_metrics"
        ).fetchone()[0] == 0


def test_formula_component_order_and_rationale_do_not_break_canonical_agreement(
    tmp_path: Path,
) -> None:
    def call_judge(
        _prompt: str,
        judge: SemanticJudgeConfig,
    ) -> SemanticJudgeBatchResponse:
        return _formula_response(
            reverse=judge.model_name == "gemini-2.5-flash",
            rationale=f"Independent explanation from {judge.model_name}",
        )

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        record = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
        )

    assert record.outcome == "unanimous_formula"
    assert len(
        set(record.target_comparisons[0].judge_canonical_json)
    ) == 1


def test_different_canonical_decisions_require_review(tmp_path: Path) -> None:
    def call_judge(
        _prompt: str,
        judge: SemanticJudgeConfig,
    ) -> SemanticJudgeBatchResponse:
        if judge.model_name == "gpt-5-mini":
            return _no_formula_response()
        return _formula_response()

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        record = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
        )

    assert record.outcome == "needs_review"
    assert record.target_comparisons[0].outcome == "needs_review"
    assert record.target_comparisons[0].unanimous_canonical_json is None


def test_three_no_formula_decisions_are_stored_as_unanimous_abstention(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        record = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=lambda _prompt, _judge: _no_formula_response(),
        )

    assert record.outcome == "unanimous_abstention"
    assert record.target_comparisons[0].outcome == "unanimous_abstention"
    assert all(
        response.response_status == "abstained"
        for response in record.judge_responses
    )


def test_three_zero_decisions_are_stored_as_unanimous_zero(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        record = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=lambda _prompt, _judge: _zero_response(),
        )

    assert record.outcome == "unanimous_zero"
    assert record.target_comparisons[0].outcome == "unanimous_zero"


def test_formula_operator_difference_requires_review(tmp_path: Path) -> None:
    def call_judge(
        _prompt: str,
        judge: SemanticJudgeConfig,
    ) -> SemanticJudgeBatchResponse:
        response = _formula_response()
        if judge.model_name == "gpt-5-mini":
            response.recommendations[0].components[1] = (
                response.recommendations[0].components[1].model_copy(
                    update={"operator": "-"}
                )
            )
        return response

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        record = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
        )

    assert record.outcome == "needs_review"
    assert record.target_comparisons[0].outcome == "needs_review"


def test_one_judge_exception_is_stored_as_a_technical_failure(
    tmp_path: Path,
) -> None:
    def call_judge(
        _prompt: str,
        judge: SemanticJudgeConfig,
    ) -> SemanticJudgeBatchResponse:
        if judge.model_name == "gemini-3.1-flash-lite":
            raise TimeoutError("judge timed out")
        return _formula_response()

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        record = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
        )

    failed = [
        response
        for response in record.judge_responses
        if response.response_status == "technical_failure"
    ]
    assert record.outcome == "technical_failure"
    assert record.target_comparisons[0].outcome == "technical_failure"
    assert len(failed) == 1
    assert "TimeoutError: judge timed out" in failed[0].error
    assert failed[0].response_json is None


def test_existing_group_is_reused_without_new_judge_calls(
    tmp_path: Path,
) -> None:
    calls = 0

    def call_judge(
        _prompt: str,
        _judge: SemanticJudgeConfig,
    ) -> SemanticJudgeBatchResponse:
        nonlocal calls
        calls += 1
        return _formula_response()

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()
        first = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
        )
        second = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
        )

    assert calls == 3
    assert second == first


def test_technical_failure_requires_explicit_retry_and_keeps_both_attempts(
    tmp_path: Path,
) -> None:
    calls = 0
    should_fail = True

    def call_judge(
        _prompt: str,
        judge: SemanticJudgeConfig,
    ) -> SemanticJudgeBatchResponse:
        nonlocal calls
        calls += 1
        if should_fail and judge.model_name == "gpt-5-mini":
            raise TimeoutError("temporary failure")
        return _formula_response()

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()
        failed = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
        )
        reused_failure = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
        )
        should_fail = False
        recovered = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=call_judge,
            retry_technical_failure=True,
        )

        attempts = repository.list_attempts(
            _group().recommendation_request_id
        )

    assert calls == 6
    assert reused_failure == failed
    assert failed.attempt_number == 1
    assert recovered.attempt_number == 2
    assert recovered.outcome == "unanimous_formula"
    assert attempts == (failed, recovered)


def test_empty_missing_target_group_is_rejected_before_judge_calls(
    tmp_path: Path,
) -> None:
    calls = 0
    group = _group()
    group = SemanticRecommendationGroup(
        recommendation_request_id=group.recommendation_request_id,
        company_id=group.company_id,
        period_ids=group.period_ids,
        judge_models=group.judge_models,
        packet=SemanticEvidencePacket(
            **{
                **group.packet.__dict__,
                "targets": (),
            }
        ),
    )

    def call_judge(
        _prompt: str,
        _judge: SemanticJudgeConfig,
    ) -> SemanticJudgeBatchResponse:
        nonlocal calls
        calls += 1
        return SemanticJudgeBatchResponse(recommendations=[])

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        with pytest.raises(ValueError, match="missing target"):
            record_semantic_recommendation_group(
                group=group,
                judges=_judges(),
                repository=repository,
                call_judge=call_judge,
            )

    assert calls == 0


def test_concurrent_insert_race_returns_the_persisted_winner(
    tmp_path: Path,
) -> None:
    group = _group()
    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()
        winner = record_semantic_recommendation_group(
            group=group,
            judges=_judges(),
            repository=repository,
            call_judge=lambda _prompt, _judge: _formula_response(),
        )

    class RacingRepository:
        def get(self, _request_id):
            return None

        def insert(self, _record):
            raise SemanticRecommendationConflictError("concurrent winner")

        def get_attempt(self, request_id, attempt_number):
            assert request_id == group.recommendation_request_id
            assert attempt_number == 1
            return winner

    raced = record_semantic_recommendation_group(
        group=group,
        judges=_judges(),
        repository=RacingRepository(),
        call_judge=lambda _prompt, _judge: _formula_response(),
    )

    assert raced == winner


def test_ineligible_component_response_becomes_a_technical_failure(
    tmp_path: Path,
) -> None:
    invalid = _formula_response()
    invalid.recommendations[0].components[0] = (
        invalid.recommendations[0].components[0].model_copy(
            update={"concept": "UnlistedConcept"}
        )
    )

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        record = record_semantic_recommendation_group(
            group=_group(),
            judges=_judges(),
            repository=repository,
            call_judge=lambda _prompt, _judge: invalid,
        )

    assert record.outcome == "technical_failure"
    assert all(
        "ineligible formula components" in response.error
        for response in record.judge_responses
    )


def _group() -> SemanticRecommendationGroup:
    packet = SemanticEvidencePacket(
        schema_version="1",
        arelle_evidence_status="available",
        targets=(
            SemanticTargetDefinition(
                metric_name="revenue",
                statement_type="income_statement",
                aliases=("sales",),
                candidate_concepts=("us-gaap:Revenue",),
                industry_labels=(),
                required_for_core=True,
                required_for_specialized_indicators=False,
            ),
        ),
        concepts=(
            SemanticConceptEvidence(
                evidence_id="concept-service-revenue",
                taxonomy="custom",
                concept="ServiceRevenue",
                label="Service revenue",
                label_source_system="arelle_structural",
                documentation="Revenue from customer services",
                documentation_source_system="arelle_structural",
                namespace_uri="https://example.com/custom",
                type_qname="xbrli:monetaryItemType",
                base_type="monetaryItemType",
                period_type="duration",
                balance="credit",
                is_numeric=True,
                is_abstract=False,
                references=(),
                source_systems=("arelle_structural",),
                source_evidence_ids=("arelle-concept-service-revenue",),
                component_eligible=True,
            ),
            SemanticConceptEvidence(
                evidence_id="concept-product-revenue",
                taxonomy="custom",
                concept="ProductRevenue",
                label="Product revenue",
                label_source_system="arelle_structural",
                documentation="Revenue from product sales",
                documentation_source_system="arelle_structural",
                namespace_uri="https://example.com/custom",
                type_qname="xbrli:monetaryItemType",
                base_type="monetaryItemType",
                period_type="duration",
                balance="credit",
                is_numeric=True,
                is_abstract=False,
                references=(),
                source_systems=("arelle_structural",),
                source_evidence_ids=("arelle-concept-product-revenue",),
                component_eligible=True,
            ),
        ),
        relationships=(),
        formula_assertions=(),
        validations=(),
        content_sha256="semantic-packet-test-hash",
    )
    return SemanticRecommendationGroup(
        recommendation_request_id="semantic-recommendation:test",
        company_id="0000000001",
        period_ids=("FY-2024", "FY-2025"),
        judge_models=(
            "gemini-2.5-flash",
            "gemini-3.1-flash-lite",
            "gpt-5-mini",
        ),
        packet=packet,
    )


def _judges() -> tuple[SemanticJudgeConfig, ...]:
    return (
        SemanticJudgeConfig("openai", "gpt-5-mini", "test-key"),
        SemanticJudgeConfig(
            "gemini",
            "gemini-3.1-flash-lite",
            "test-key",
        ),
        SemanticJudgeConfig("gemini", "gemini-2.5-flash", "test-key"),
    )


def _formula_response(
    *,
    reverse: bool = False,
    rationale: str = "The extension concepts report company revenue.",
) -> SemanticJudgeBatchResponse:
    components = [
        SemanticFormulaComponentResponse(
            taxonomy="custom",
            concept="ServiceRevenue",
            operator="+",
            evidence_refs=["concept-service-revenue"],
        ),
        SemanticFormulaComponentResponse(
            taxonomy="custom",
            concept="ProductRevenue",
            operator="+",
            evidence_refs=["concept-product-revenue"],
        ),
    ]
    if reverse:
        components.reverse()
    return SemanticJudgeBatchResponse(
        recommendations=[
            SemanticTargetRecommendationResponse(
                target_metric_name="revenue",
                statement_type="income_statement",
                decision="formula",
                components=components,
                evidence_refs=[
                    "concept-product-revenue",
                    "concept-service-revenue",
                ],
                rationale=rationale,
            )
        ]
    )


def _no_formula_response() -> SemanticJudgeBatchResponse:
    return SemanticJudgeBatchResponse(
        recommendations=[
            SemanticTargetRecommendationResponse(
                target_metric_name="revenue",
                statement_type="income_statement",
                decision="no_formula",
                components=[],
                evidence_refs=[],
                rationale="The packet does not support a formula or zero.",
            )
        ]
    )


def _zero_response() -> SemanticJudgeBatchResponse:
    return SemanticJudgeBatchResponse(
        recommendations=[
            SemanticTargetRecommendationResponse(
                target_metric_name="revenue",
                statement_type="income_statement",
                decision="zero",
                components=[],
                evidence_refs=["concept-service-revenue"],
                rationale="The supplied concept evidence affirmatively supports zero.",
            )
        ]
    )
