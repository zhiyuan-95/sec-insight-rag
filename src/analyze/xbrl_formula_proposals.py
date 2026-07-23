"""LLM provider calls for report-only XBRL formula proposals."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from src.analyze.prompts import (
    build_xbrl_formula_proposal_batch_prompt,
    build_xbrl_formula_proposal_prompt,
)
from src.analyze.structured_json import (
    generate_openai_json,
    openai_temperature,
)
from src.model_defaults import (
    DEFAULT_GEMINI_FLASH_LITE_JUDGE_MODEL,
    DEFAULT_GEMINI_JUDGE_MODEL,
    DEFAULT_OPENAI_JUDGE_MODEL,
)
from src.processing.formula_proposals import (
    FORMULA_PROPOSAL_BATCH_RESPONSE_JSON_SCHEMA,
    FORMULA_PROPOSAL_RESPONSE_JSON_SCHEMA,
    FormulaProposalBatchResponse,
    FormulaProposalProviderResult,
    FormulaProposalResponse,
    FormulaProposalTarget,
    coerce_formula_proposal_batch_response,
    coerce_formula_proposal_response,
    provider_failed_result,
    provider_result_from_response,
    provider_unavailable_result,
)

DEFAULT_GEMINI_FORMULA_PROPOSAL_MODEL = DEFAULT_GEMINI_JUDGE_MODEL
DEFAULT_GEMINI_FLASH_LITE_FORMULA_PROPOSAL_MODEL = (
    DEFAULT_GEMINI_FLASH_LITE_JUDGE_MODEL
)
DEFAULT_OPENAI_FORMULA_PROPOSAL_MODEL = DEFAULT_OPENAI_JUDGE_MODEL

FormulaJsonGenerator = Callable[[str, type[BaseModel], str], object]


@dataclass(frozen=True)
class FormulaProposalProviderConfig:
    """Runtime provider configuration for formula proposal calls."""

    provider_name: str
    model_name: str
    api_key: str | None = None


def default_formula_proposal_provider_configs(
    *,
    gemini_api_key: str | None,
    openai_api_key: str | None,
    gemini_model: str = DEFAULT_GEMINI_FORMULA_PROPOSAL_MODEL,
    gemini_flash_lite_model: str = DEFAULT_GEMINI_FLASH_LITE_FORMULA_PROPOSAL_MODEL,
    openai_model: str = DEFAULT_OPENAI_FORMULA_PROPOSAL_MODEL,
) -> tuple[FormulaProposalProviderConfig, ...]:
    """Return the configured formula proposal provider panel."""
    configs = (
        FormulaProposalProviderConfig("openai", openai_model, openai_api_key),
        FormulaProposalProviderConfig("gemini", gemini_flash_lite_model, gemini_api_key),
        FormulaProposalProviderConfig("gemini", gemini_model, gemini_api_key),
    )
    identities = [
        (config.provider_name.strip().lower(), config.model_name.strip().lower())
        for config in configs
    ]
    if len(set(identities)) != len(identities):
        duplicates = sorted(
            f"{provider}/{model}"
            for provider, model in set(identities)
            if identities.count((provider, model)) > 1
        )
        raise ValueError(
            "formula proposal provider/model slots must be unique: "
            + ", ".join(duplicates)
        )
    return configs


def generate_formula_proposal(
    *,
    ticker: str,
    cik: str,
    target: FormulaProposalTarget,
    fact_pool: list[dict[str, object]],
    provider: FormulaProposalProviderConfig,
    formula_context: dict[str, object] | None = None,
    generate_json: FormulaJsonGenerator | None = None,
) -> FormulaProposalProviderResult:
    """Generate one provider formula proposal or a reportable failure row."""
    if not provider.api_key:
        return provider_unavailable_result(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target=target,
            reason=f"{provider.provider_name} API key is not configured",
        )
    prompt = build_xbrl_formula_proposal_prompt(
        ticker=ticker,
        cik=cik,
        target=_target_prompt_payload(target),
        fact_pool=fact_pool,
        formula_context=formula_context,
    )
    try:
        if generate_json is not None:
            payload = generate_json(prompt, FormulaProposalResponse, provider.model_name)
        elif provider.provider_name == "gemini":
            payload = _generate_gemini_json(
                prompt=prompt,
                model=provider.model_name,
                api_key=provider.api_key,
            )
        elif provider.provider_name == "openai":
            payload = generate_openai_json(
                prompt=prompt,
                model=provider.model_name,
                api_key=provider.api_key,
                schema=FORMULA_PROPOSAL_RESPONSE_JSON_SCHEMA,
                schema_name="xbrl_formula_proposal",
                system_content="Return only valid JSON for the requested XBRL formula proposal schema.",
                temperature=openai_temperature(provider.model_name),
            )
        else:
            return provider_unavailable_result(
                provider_name=provider.provider_name,
                model_name=provider.model_name,
                target=target,
                reason=f"unsupported formula proposal provider: {provider.provider_name}",
            )
        response = coerce_formula_proposal_response(payload)
    except Exception as exc:
        return provider_failed_result(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target=target,
            error=str(exc),
        )
    return provider_result_from_response(
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        target=target,
        response=response,
    )


def generate_formula_proposal_batch(
    *,
    ticker: str,
    cik: str,
    targets: list[FormulaProposalTarget],
    fact_pool: list[dict[str, object]],
    provider: FormulaProposalProviderConfig,
    formula_context: dict[str, object] | None = None,
    generate_json: FormulaJsonGenerator | None = None,
) -> tuple[FormulaProposalProviderResult, ...]:
    """Generate one provider call for multiple same-statement targets.

    Malformed or target-incomplete responses raise ``ValueError`` so callers can
    retry the same work as single-target requests.
    """
    if not targets:
        return ()
    if not provider.api_key:
        return tuple(
            provider_unavailable_result(
                provider_name=provider.provider_name,
                model_name=provider.model_name,
                target=target,
                reason=f"{provider.provider_name} API key is not configured",
            )
            for target in targets
        )
    prompt = build_xbrl_formula_proposal_batch_prompt(
        ticker=ticker,
        cik=cik,
        targets=[_target_prompt_payload(target) for target in targets],
        fact_pool=fact_pool,
        formula_context=formula_context,
    )
    try:
        if generate_json is not None:
            payload = generate_json(prompt, FormulaProposalBatchResponse, provider.model_name)
        elif provider.provider_name == "gemini":
            payload = _generate_gemini_batch_json(
                prompt=prompt,
                model=provider.model_name,
                api_key=provider.api_key,
            )
        elif provider.provider_name == "openai":
            payload = generate_openai_json(
                prompt=prompt,
                model=provider.model_name,
                api_key=provider.api_key,
                schema=FORMULA_PROPOSAL_BATCH_RESPONSE_JSON_SCHEMA,
                schema_name="xbrl_formula_proposal_batch",
                system_content="Return only valid JSON for the requested XBRL formula proposal batch schema.",
                temperature=openai_temperature(provider.model_name),
            )
        else:
            return tuple(
                provider_unavailable_result(
                    provider_name=provider.provider_name,
                    model_name=provider.model_name,
                    target=target,
                    reason=f"unsupported formula proposal provider: {provider.provider_name}",
                )
                for target in targets
            )
    except Exception as exc:
        return tuple(
            provider_failed_result(
                provider_name=provider.provider_name,
                model_name=provider.model_name,
                target=target,
                error=str(exc),
            )
            for target in targets
        )

    batch_response = coerce_formula_proposal_batch_response(payload)
    return _provider_results_from_batch_response(
        provider=provider,
        targets=targets,
        response=batch_response,
    )


def _generate_gemini_json(*, prompt: str, model: str, api_key: str) -> object:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("google-genai is not installed; cannot call Gemini") from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": FormulaProposalResponse,
        },
    )
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return parsed
    return getattr(response, "text", "")


def _generate_gemini_batch_json(*, prompt: str, model: str, api_key: str) -> object:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("google-genai is not installed; cannot call Gemini") from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": FormulaProposalBatchResponse,
        },
    )
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return parsed
    return getattr(response, "text", "")


def _target_prompt_payload(target: FormulaProposalTarget) -> dict[str, object]:
    return {
        "target_metric_name": target.target_metric_name,
        "target_xbrl_concept": target.target_xbrl_concept,
        "taxonomy": target.taxonomy,
        "concept": target.concept,
        "statement_type": target.statement_type,
        "industry_label": target.industry_label,
        "notes": target.notes,
    }


def _provider_results_from_batch_response(
    *,
    provider: FormulaProposalProviderConfig,
    targets: list[FormulaProposalTarget],
    response: FormulaProposalBatchResponse,
) -> tuple[FormulaProposalProviderResult, ...]:
    if len(response.proposals) != len(targets):
        raise ValueError(
            "formula proposal batch returned "
            f"{len(response.proposals)} proposal(s) for {len(targets)} target(s)"
        )
    targets_by_key = {_target_response_key(target): target for target in targets}
    if len(targets_by_key) != len(targets):
        raise ValueError("formula proposal batch targets include duplicate identities")

    responses_by_key: dict[tuple[str, str], FormulaProposalResponse] = {}
    for proposal in response.proposals:
        key = _response_key(proposal)
        if key not in targets_by_key:
            raise ValueError(
                "formula proposal batch returned an unexpected target: "
                f"{proposal.target_metric_name} / {proposal.target_xbrl_concept}"
            )
        if key in responses_by_key:
            raise ValueError(
                "formula proposal batch returned duplicate target: "
                f"{proposal.target_metric_name} / {proposal.target_xbrl_concept}"
            )
        responses_by_key[key] = proposal

    missing = [target for target in targets if _target_response_key(target) not in responses_by_key]
    if missing:
        names = ", ".join(target.target_metric_name for target in missing)
        raise ValueError(f"formula proposal batch omitted target(s): {names}")

    return tuple(
        provider_result_from_response(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target=target,
            response=responses_by_key[_target_response_key(target)],
        )
        for target in targets
    )


def _target_response_key(target: FormulaProposalTarget) -> tuple[str, str]:
    return (
        str(target.target_metric_name or "").strip().lower(),
        str(target.target_xbrl_concept or "").strip().lower(),
    )


def _response_key(response: FormulaProposalResponse) -> tuple[str, str]:
    return (
        str(response.target_metric_name or "").strip().lower(),
        str(response.target_xbrl_concept or "").strip().lower(),
    )
