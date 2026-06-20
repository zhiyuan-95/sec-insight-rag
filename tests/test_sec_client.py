import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from src.ingestion import SecClient, SecConfigurationError, SecHttpError, SecJsonError


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.body = body
        self.headers = headers or {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _header(request: Request, name: str) -> str | None:
    for key, value in request.header_items():
        if key.lower() == name.lower():
            return value
    return None


def test_sec_client_rejects_blank_user_agent() -> None:
    with pytest.raises(SecConfigurationError):
        SecClient(" ")


def test_get_json_adds_sec_headers_and_parses_response() -> None:
    captured: dict[str, Request] = {}

    def opener(request: Request, timeout: float) -> FakeResponse:
        captured["request"] = request
        assert timeout == 30.0
        return FakeResponse(json.dumps({"ok": True}).encode("utf-8"))

    client = SecClient(
        "Example contact@example.com",
        opener=opener,
        min_request_interval_seconds=0,
    )

    assert client.get_json("https://data.sec.gov/example.json") == {"ok": True}
    assert _header(captured["request"], "User-Agent") == "Example contact@example.com"
    assert _header(captured["request"], "Accept") == "application/json"
    assert _header(captured["request"], "Accept-Encoding") == "gzip, deflate"


def test_get_json_raises_for_invalid_json() -> None:
    client = SecClient(
        "Example contact@example.com",
        opener=lambda request, timeout: FakeResponse(b"not json"),
        min_request_interval_seconds=0,
    )

    with pytest.raises(SecJsonError):
        client.get_json("https://data.sec.gov/example.json")


def test_get_bytes_does_not_retry_non_retryable_http_error() -> None:
    calls = 0

    def opener(request: Request, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    client = SecClient(
        "Example contact@example.com",
        opener=opener,
        max_retries=3,
        min_request_interval_seconds=0,
    )

    with pytest.raises(SecHttpError) as exc_info:
        client.get_bytes("https://data.sec.gov/forbidden")

    assert calls == 1
    assert exc_info.value.status_code == 403


def test_get_bytes_retries_retryable_http_error() -> None:
    calls = 0

    def opener(request: Request, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(request.full_url, 500, "Server Error", hdrs=None, fp=None)
        return FakeResponse(b"ok")

    client = SecClient(
        "Example contact@example.com",
        opener=opener,
        max_retries=1,
        retry_backoff_seconds=0,
        min_request_interval_seconds=0,
    )

    assert client.get_bytes("https://data.sec.gov/retry") == b"ok"
    assert calls == 2
