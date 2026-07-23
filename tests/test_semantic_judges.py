import pytest

from src.analyze.semantic_judges import (
    SemanticJudgeConfig,
    default_semantic_judge_configs,
    generate_semantic_judgment,
)
from src.processing.semantic_recommendations import (
    SEMANTIC_JUDGE_BATCH_RESPONSE_JSON_SCHEMA,
    SemanticJudgeBatchResponse,
)


def test_default_semantic_judge_lineup_uses_the_configured_three_models() -> None:
    judges = default_semantic_judge_configs(
        gemini_api_key="gemini-key",
        openai_api_key="openai-key",
    )

    assert tuple(judge.model_name for judge in judges) == (
        "gpt-5-mini",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
    )
    assert len({judge.model_name for judge in judges}) == 3


def test_semantic_judge_injected_generator_receives_structured_schema() -> None:
    observed = {}

    def generate_json(prompt, response_type, model):
        observed.update(
            prompt=prompt,
            response_type=response_type,
            model=model,
        )
        return {"recommendations": []}

    result = generate_semantic_judgment(
        "shared prompt",
        SemanticJudgeConfig("openai", "gpt-5-mini", "test-key"),
        generate_json=generate_json,
    )

    assert result == {"recommendations": []}
    assert observed == {
        "prompt": "shared prompt",
        "response_type": SemanticJudgeBatchResponse,
        "model": "gpt-5-mini",
    }


def test_semantic_judge_without_credentials_fails_explicitly() -> None:
    with pytest.raises(RuntimeError, match="API key is not configured"):
        generate_semantic_judgment(
            "shared prompt",
            SemanticJudgeConfig("gemini", "gemini-2.5-flash"),
        )


def test_semantic_judge_openai_schema_is_strict_and_fully_required() -> None:
    schema = SEMANTIC_JUDGE_BATCH_RESPONSE_JSON_SCHEMA
    target_schema = schema["$defs"]["SemanticTargetRecommendationResponse"]
    component_schema = schema["$defs"]["SemanticFormulaComponentResponse"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert target_schema["additionalProperties"] is False
    assert set(target_schema["required"]) == set(target_schema["properties"])
    assert component_schema["additionalProperties"] is False
    assert set(component_schema["required"]) == set(
        component_schema["properties"]
    )
