"""Shared HTTP boundary for the standalone SDK; no server imports."""

from __future__ import annotations

import math
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit

import httpx
from pydantic import TypeAdapter, ValidationError

JSON = dict[str, Any]
T = TypeVar("T")


class ResponseValidationError(RuntimeError):
    """The server response does not match a known SDK contract."""


def _validated(response: httpx.Response, adapter: TypeAdapter[T]) -> T:
    try:
        payload = response.json()
        adapter.validate_python(payload, strict=True)
    except (ValueError, ValidationError):
        # Do not include personal data or an untrusted response in diagnostics.
        raise ResponseValidationError("Invalid Resume Harness API response") from None
    # Retain additive fields for forward compatibility after checking known ones.
    return cast(T, payload)


class APIError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        super().__init__(f"{code}: {message}")
        self.status_code, self.code, self.details = status_code, code, details


class RunFailed(RuntimeError):
    def __init__(self, run: JSON):
        self.run = run
        super().__init__(
            f"Run {run['runId']} {run['state']}: {run.get('error') or 'no result'}"
        )


class RunTimeout(TimeoutError):
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(
            f"Timed out waiting for {run_id}; the server run may still be active"
        )


def _positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def _id(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("ID must be a positive integer")
    return str(value)


class _Transport:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
    ):
        _positive(timeout, "timeout")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "base_url must be an HTTP(S) deployment URL without credentials, query, or fragment"
            )
        if parsed.scheme == "http" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Use HTTPS except for a loopback development server")
        if not api_key.strip() or any(c.isspace() for c in api_key):
            raise ValueError("api_key must be a nonempty token without whitespace")
        base = base_url.rstrip("/")
        if not base.endswith("/api"):
            base += "/api"
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=base + "/",
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "resume-harness-sdk/0.5.0",
            },
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        if not response.is_success:
            try:
                payload = response.json()
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                if not isinstance(error, dict):
                    error = {}
            except ValueError:
                error = {}
            # Do not echo raw HTML, credentials, request bodies, or proxy errors.
            raise APIError(
                response.status_code,
                error.get("code", "HTTP_ERROR"),
                error.get("message", f"HTTP {response.status_code}"),
                error.get("details"),
            )
        return response
