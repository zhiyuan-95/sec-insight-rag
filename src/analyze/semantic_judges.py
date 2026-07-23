"""Provider calls for production semantic recommendation judges."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from src.analyze.structured_json import (
    generate_openai_json,
    openai_temperature,
)
from src.model_defaults import (
    DEFAULT_GEMINI_FLASH_LITE_JUDGE_MODEL,
    DEFAULT_GEMINI_JUDGE_MODEL,
    DEFAULT_OPENAI_JUDGE_MODEL,
)
from src.processing.semantic_recommendations import (
    SEMANTIC_JUDGE_BATCH_RESPONSE_JSON_SCHEMA,
    SemanticJudgeBatchResponse,
)

SemanticJsonGenerator = Callable[[str, type[BaseModel], str], object]


@dataclass(frozen=True)
class SemanticJudgeConfig:
    """Runtime provider and model configuration for one judge slot."""

    provider_name: str
    model_name: str
    api_key: str | None = None


def default_semantic_judge_configs(
    *,
    gemini_api_key: str | None,
    openai_api_key: str | None,
    gemini_model: str = DEFAULT_GEMINI_JUDGE_MODEL,
    gemini_flash_lite_model: str = (
        DEFAULT_GEMINI_FLASH_LITE_JUDGE_MODEL
    ),
    openai_model: str = DEFAULT_OPENAI_JUDGE_MODEL,
) -> tuple[SemanticJudgeConfig, ...]:
    """Return the configured independent three-model judge lineup."""
    judges = (
        SemanticJudgeConfig("openai", openai_model, openai_api_key),
        SemanticJudgeConfig(
            "gemini",
            gemini_flash_lite_model,
            gemini_api_key,
        ),
        SemanticJudgeConfig("gemini", gemini_model, gemini_api_key),
    )
    identities = {
        (judge.provider_name.casefold(), judge.model_name.casefold())
        for judge in judges
    }
    if len(identities) != 3 or len({judge.model_name for judge in judges}) != 3:
        raise ValueError("exactly three distinct semantic judge models are required")
    return judges


def generate_semantic_judgment(
    prompt: str,
    judge: SemanticJudgeConfig,
    *,
    generate_json: SemanticJsonGenerator | None = None,
) -> object:
    """Call one semantic judge and return its structured response payload."""
    if not judge.api_key:
        raise RuntimeError(
            f"{judge.provider_name} API key is not configured"
        )
    if generate_json is not None:
        return generate_json(
            prompt,
            SemanticJudgeBatchResponse,
            judge.model_name,
        )
    if judge.provider_name == "gemini":
        return _generate_gemini_semantic_json(
            prompt=prompt,
            model=judge.model_name,
            api_key=judge.api_key,
        )
    if judge.provider_name == "openai":
        return generate_openai_json(
            prompt=prompt,
            model=judge.model_name,
            api_key=judge.api_key,
            schema=SEMANTIC_JUDGE_BATCH_RESPONSE_JSON_SCHEMA,
            schema_name="semantic_recommendation",
            system_content=(
                "Return only valid JSON for the semantic recommendation schema."
            ),
            temperature=openai_temperature(judge.model_name),
        )
    raise ValueError(
        f"unsupported semantic judge provider: {judge.provider_name}"
    )


def _generate_gemini_semantic_json(
    *,
    prompt: str,
    model: str,
    api_key: str,
) -> object:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed; cannot call Gemini"
        ) from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": SemanticJudgeBatchResponse,
        },
    )
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return parsed
    return getattr(response, "text", "")
