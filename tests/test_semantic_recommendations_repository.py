from dataclasses import replace
from pathlib import Path

import pytest

from src.processing.semantic_recommendations import (
    SemanticJudgeIdentity,
    SemanticJudgeResponseRecord,
    SemanticRecommendationRecord,
    SemanticTargetComparison,
)
from src.storage import (
    SemanticRecommendationConflictError,
    SemanticRecommendationRepository,
    connect_sqlite,
)


def test_semantic_recommendation_record_round_trips_exactly(
    tmp_path: Path,
) -> None:
    lineup = (
        SemanticJudgeIdentity("openai", "gpt-5-mini"),
        SemanticJudgeIdentity("gemini", "gemini-3.1-flash-lite"),
        SemanticJudgeIdentity("gemini", "gemini-2.5-flash"),
    )
    response_json = (
        '{"recommendations":[{"decision":"formula",'
        '"target_metric_name":"revenue"}]}'
    )
    record = SemanticRecommendationRecord(
        recommendation_request_id="semantic-recommendation:test",
        attempt_number=1,
        company_id="0000000001",
        period_ids=("FY-2024", "FY-2025"),
        packet_content_sha256="packet-hash",
        packet_json='{"schema_version":"1"}',
        prompt_version="semantic_recommendation_v1",
        judge_lineup=lineup,
        judge_responses=tuple(
            SemanticJudgeResponseRecord(
                judge=judge,
                response_status="completed",
                started_at="2026-07-23T12:00:00+00:00",
                completed_at="2026-07-23T12:00:01+00:00",
                response_json=response_json,
                canonical_response_json='{"decision":"formula"}',
                error="",
            )
            for judge in lineup
        ),
        target_comparisons=(
            SemanticTargetComparison(
                target_metric_name="revenue",
                statement_type="income_statement",
                outcome="unanimous_formula",
                judge_canonical_json=(
                    '{"decision":"formula"}',
                    '{"decision":"formula"}',
                    '{"decision":"formula"}',
                ),
                unanimous_canonical_json='{"decision":"formula"}',
            ),
        ),
        outcome="unanimous_formula",
        created_at="2026-07-23T12:00:02+00:00",
    )

    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = SemanticRecommendationRepository(connection)
        repository.initialize()

        assert repository.insert(record) is True
        assert repository.insert(record) is False
        assert repository.get(record.recommendation_request_id) == record
        assert repository.list_attempts(
            record.recommendation_request_id
        ) == (record,)

        with pytest.raises(
            SemanticRecommendationConflictError,
            match="immutable semantic recommendation",
        ):
            repository.insert(
                SemanticRecommendationRecord(
                    **{
                        **record.__dict__,
                        "outcome": "needs_review",
                    }
                )
            )

        with pytest.raises(ValueError, match="attempt_number"):
            repository.insert(replace(record, attempt_number=0))
