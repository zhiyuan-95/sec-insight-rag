"""LLM provider calls for report-only XBRL formula proposals."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from src.analyze.prompts import (
    build_xbrl_formula_proposal_batch_prompt,
    build_xbrl_formula_proposal_prompt,
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

DEFAULT_GEMINI_FORMULA_PROPOSAL_MODEL = "gemini-2.5-flash"
DEFAULT_ANTHROPIC_FORMULA_PROPOSAL_MODEL = "claude-sonnet-5"
DEFAULT_OPENAI_FORMULA_PROPOSAL_MODEL = "gpt-5-mini"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 8192
HTTP_TIMEOUT_SECONDS = 120

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
    anthropic_api_key: str | None,
    gemini_model: str = DEFAULT_GEMINI_FORMULA_PROPOSAL_MODEL,
    openai_model: str = DEFAULT_OPENAI_FORMULA_PROPOSAL_MODEL,
) -> tuple[FormulaProposalProviderConfig, ...]:
    """Return the configured formula proposal provider panel."""
    configs = (
        FormulaProposalProviderConfig("openai", openai_model, openai_api_key),
        FormulaProposalProviderConfig(
            "anthropic",
            DEFAULT_ANTHROPIC_FORMULA_PROPOSAL_MODEL,
            anthropic_api_key,
        ),
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
            payload = _generate_openai_json(
                prompt=prompt,
                model=provider.model_name,
                api_key=provider.api_key,
                schema=FORMULA_PROPOSAL_RESPONSE_JSON_SCHEMA,
                schema_name="xbrl_formula_proposal",
                system_content="Return only valid JSON for the requested XBRL formula proposal schema.",
                temperature=_openai_temperature(provider.model_name),
            )
        elif provider.provider_name == "anthropic":
            payload = _generate_anthropic_json(
                prompt=prompt,
                model=provider.model_name,
                api_key=provider.api_key,
                schema=FORMULA_PROPOSAL_RESPONSE_JSON_SCHEMA,
                system_content="Return only valid JSON for the requested XBRL formula proposal schema.",
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
            error=_provider_error_text(provider, exc),
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
            payload = _generate_openai_json(
                prompt=prompt,
                model=provider.model_name,
                api_key=provider.api_key,
                schema=FORMULA_PROPOSAL_BATCH_RESPONSE_JSON_SCHEMA,
                schema_name="xbrl_formula_proposal_batch",
                system_content="Return only valid JSON for the requested XBRL formula proposal batch schema.",
                temperature=_openai_temperature(provider.model_name),
            )
        elif provider.provider_name == "anthropic":
            payload = _generate_anthropic_json(
                prompt=prompt,
                model=provider.model_name,
                api_key=provider.api_key,
                schema=FORMULA_PROPOSAL_BATCH_RESPONSE_JSON_SCHEMA,
                system_content="Return only valid JSON for the requested XBRL formula proposal batch schema.",
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
                error=_provider_error_text(provider, exc),
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


def _generate_openai_json(
    *,
    prompt: str,
    model: str,
    api_key: str,
    schema: dict[str, object],
    schema_name: str,
    system_content: str,
    temperature: float | None = 0,
) -> object:
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": system_content,
            },
            {"role": "user", "content": prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    if temperature is not None:
        payload["temperature"] = temperature
    data = _post_json(
        OPENAI_RESPONSES_URL,
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
        redaction_values=(api_key,),
    )
    return _extract_openai_response_text(data)


def _generate_anthropic_json(
    *,
    prompt: str,
    model: str,
    api_key: str,
    schema: dict[str, object],
    system_content: str,
) -> object:
    payload = {
        "model": model,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "system": system_content,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": "medium",
            "format": {
                "type": "json_schema",
                "schema": _anthropic_compatible_schema(schema),
            },
        },
    }
    data = _post_json(
        ANTHROPIC_MESSAGES_URL,
        payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
        },
        redaction_values=(api_key,),
    )
    return _extract_anthropic_response_text(data)


def _anthropic_compatible_schema(
    schema: dict[str, object],
) -> dict[str, object]:
    """Copy a schema without numeric bounds unsupported by Anthropic.

    The shared Pydantic response models still enforce these bounds after the
    provider response is parsed.
    """

    def clean(value: object) -> object:
        if isinstance(value, list):
            return [clean(item) for item in value]
        if not isinstance(value, dict):
            return value

        unsupported_keys = (
            {"minimum", "maximum"}
            if value.get("type") in {"number", "integer"}
            else set()
        )
        return {
            key: clean(item)
            for key, item in value.items()
            if key not in unsupported_keys
        }

    compatible = clean(schema)
    if not isinstance(compatible, dict):
        raise TypeError("Anthropic structured output schema must be an object")
    return compatible


def _openai_temperature(model: str) -> float | None:
    """Return the compatibility-proven temperature option for an OpenAI model."""
    if str(model or "").strip().lower() == DEFAULT_OPENAI_FORMULA_PROPOSAL_MODEL:
        return None
    return 0


def _post_json(
    url: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str],
    redaction_values: Iterable[str] = (),
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        safe_detail = _redact_sensitive_text(detail, redaction_values)
        raise RuntimeError(f"HTTP {exc.code} from provider: {safe_detail[:500]}") from None
    return json.loads(raw)


def _redact_sensitive_text(text: str, sensitive_values: Iterable[str]) -> str:
    redacted = text
    values = sorted(
        {str(value) for value in sensitive_values if str(value)},
        key=len,
        reverse=True,
    )
    for value in values:
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def _provider_error_text(
    provider: FormulaProposalProviderConfig,
    error: Exception,
) -> str:
    sensitive_values = (provider.api_key,) if provider.api_key else ()
    return _redact_sensitive_text(str(error), sensitive_values)


def _extract_openai_response_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    raise RuntimeError("OpenAI response did not include output text")


def _extract_anthropic_response_text(data: dict[str, Any]) -> str:
    if data.get("stop_reason") != "end_turn":
        raise RuntimeError("Anthropic response did not complete with end_turn")

    content = data.get("content")
    if not isinstance(content, list):
        raise RuntimeError("Anthropic response did not include valid content")

    text_blocks: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            raise RuntimeError("Anthropic response included an unsupported content block")
        block_type = block.get("type")
        if block_type in {"thinking", "redacted_thinking"}:
            continue
        if block_type != "text":
            raise RuntimeError("Anthropic response included an unsupported content block")
        text = block.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Anthropic response included an empty text block")
        text_blocks.append(text)

    if len(text_blocks) != 1:
        raise RuntimeError("Anthropic response must include exactly one text block")
    return text_blocks[0]


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
