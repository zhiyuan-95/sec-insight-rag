"""Small SEC HTTP client with fair-access behavior."""

from __future__ import annotations

import gzip
import json
import time
import zlib
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.ingestion.errors import SecConfigurationError, SecHttpError, SecJsonError

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class SecClient:
    """HTTP client for SEC endpoints."""

    def __init__(
        self,
        user_agent: str | None,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        min_request_interval_seconds: float = 0.1,
        opener: Callable[..., Any] | None = None,
        sleep_func: Callable[[float], None] = time.sleep,
        monotonic_func: Callable[[], float] = time.monotonic,
    ) -> None:
        if user_agent is None or not user_agent.strip():
            raise SecConfigurationError("SEC_USER_AGENT is required for SEC ingestion")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        if min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds cannot be negative")

        self.user_agent = user_agent.strip()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.min_request_interval_seconds = min_request_interval_seconds
        self._opener = opener or urlopen
        self._sleep = sleep_func
        self._monotonic = monotonic_func
        self._last_request_at: float | None = None

    def get_json(self, url: str) -> dict[str, Any]:
        """Fetch and parse an SEC JSON response."""
        body = self.get_bytes(url, accept="application/json")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SecJsonError(f"SEC response was not valid JSON: {url}") from exc
        if not isinstance(payload, dict):
            raise SecJsonError(f"SEC JSON response was not an object: {url}")
        return payload

    def get_bytes(self, url: str, *, accept: str = "*/*") -> bytes:
        """Fetch bytes from an SEC URL."""
        attempts = self.max_retries + 1
        last_error: SecHttpError | None = None

        for attempt_index in range(attempts):
            self._throttle()
            request = self._build_request(url, accept=accept)
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    body = response.read()
                    headers = getattr(response, "headers", {})
                    self._last_request_at = self._monotonic()
                    return _decode_body(body, _get_header(headers, "Content-Encoding"))
            except HTTPError as exc:
                self._last_request_at = self._monotonic()
                last_error = SecHttpError(
                    f"SEC request failed with status {exc.code}: {url}",
                    status_code=exc.code,
                    url=url,
                )
                if not _should_retry(exc.code, attempt_index, attempts):
                    raise last_error from exc
            except URLError as exc:
                self._last_request_at = self._monotonic()
                last_error = SecHttpError(f"SEC request failed: {url}", url=url)
                if attempt_index == attempts - 1:
                    raise last_error from exc

            if attempt_index < attempts - 1 and self.retry_backoff_seconds:
                self._sleep(self.retry_backoff_seconds * (attempt_index + 1))

        if last_error is not None:
            raise last_error
        raise SecHttpError(f"SEC request failed: {url}", url=url)

    def _build_request(self, url: str, *, accept: str) -> Request:
        return Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": accept,
                "Accept-Encoding": "gzip, deflate",
            },
        )

    def _throttle(self) -> None:
        if self._last_request_at is None or self.min_request_interval_seconds == 0:
            return
        elapsed = self._monotonic() - self._last_request_at
        remaining = self.min_request_interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)


def _should_retry(status_code: int, attempt_index: int, attempts: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES and attempt_index < attempts - 1


def _decode_body(body: bytes, content_encoding: str | None) -> bytes:
    if content_encoding is None:
        return body
    encoding = content_encoding.lower()
    if encoding == "gzip":
        return gzip.decompress(body)
    if encoding == "deflate":
        return zlib.decompress(body)
    return body


def _get_header(headers: Any, name: str) -> str | None:
    if hasattr(headers, "get"):
        value = headers.get(name)
        if value is None:
            value = headers.get(name.lower())
        return value
    return None
