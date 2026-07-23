"""Shared OpenAI structured-JSON transport for analysis providers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from src.model_defaults import DEFAULT_OPENAI_JUDGE_MODEL

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
HTTP_TIMEOUT_SECONDS = 120


def generate_openai_json(
    *,
    prompt: str,
    model: str,
    api_key: str,
    schema: dict[str, object],
    schema_name: str,
    system_content: str,
    temperature: float | None = 0,
) -> object:
    """Request one strict structured-JSON response from OpenAI."""
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
    )
    return _extract_openai_response_text(data)


def openai_temperature(model: str) -> float | None:
    """Return the compatibility-proven temperature option for a judge model."""
    if str(model or "").strip().casefold() == DEFAULT_OPENAI_JUDGE_MODEL:
        return None
    return 0


def _post_json(
    url: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str],
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
        with urllib.request.urlopen(
            request,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} from provider: {detail[:500]}"
        ) from exc
    return json.loads(raw)


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
