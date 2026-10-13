from __future__ import annotations

import math
import os
import time
from collections.abc import Iterator
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx

JSON = dict[str, Any]


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


class ResumeHarness:
    """Synchronous API client. Responses preserve the API's JSON field names.

    base_url is the deployment origin (optionally ending in /api). API keys are
    personal access tokens, not an OpenAI/Anthropic key. Writes are never retried.
    """

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
                "User-Agent": "resume-harness-sdk/0.1.0",
            },
            follow_redirects=False,
        )

    @classmethod
    def from_env(cls, **kwargs) -> ResumeHarness:
        """Read RESUME_HARNESS_URL and RESUME_HARNESS_API_KEY."""
        return cls(
            base_url=os.environ["RESUME_HARNESS_URL"],
            api_key=os.environ["RESUME_HARNESS_API_KEY"],
            **kwargs,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ResumeHarness:
        return self

    def __exit__(self, *args) -> None:
        self.close()

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

    def me(self) -> JSON:
        return self._request("GET", "auth/me").json()

    def list_jobs(
        self,
        *,
        board: Literal["triage", "shortlist", "pipeline"] = "triage",
        page: int = 1,
        page_size: int = 50,
        **filters: Any,
    ) -> JSON:
        if board not in {"triage", "shortlist", "pipeline"}:
            raise ValueError("board must be triage, shortlist, or pipeline")
        return self._request(
            "GET", board, params={**filters, "page": page, "pageSize": page_size}
        ).json()

    def iter_jobs(
        self,
        *,
        board: Literal["triage", "shortlist", "pipeline"] = "triage",
        page_size: int = 50,
        **filters: Any,
    ) -> Iterator[JSON]:
        page = 1
        while True:
            result = self.list_jobs(
                board=board, page=page, page_size=page_size, **filters
            )
            yield from result["data"]
            if not result["data"] or page >= result["pagination"]["totalPages"]:
                return
            page += 1

    def get_job(self, job_id: int) -> JSON:
        return self._request("GET", f"jobs/{_id(job_id)}").json()

    def list_sources(self) -> Any:
        return self._request("GET", "sources").json()

    def pull_jobs(
        self,
        *,
        source_ids: list[str] | None = None,
        limit: int | None = None,
        refresh: bool = False,
    ) -> JSON:
        return self._request(
            "POST",
            "pull",
            json={"sourceIds": source_ids, "limit": limit, "refresh": refresh},
        ).json()

    def discover_jobs(self) -> JSON:
        return self._request("POST", "discover", json={}).json()

    def add_job(self, *, jd_text: str, **metadata: Any) -> JSON:
        return self._request(
            "POST", "jobs", json={**metadata, "jdText": jd_text}
        ).json()

    def tailor(self, job_ids: list[int], *, deep: bool = False) -> JSON:
        if not job_ids:
            raise ValueError("Provide at least one job ID")
        for job_id in job_ids:
            _id(job_id)
        return self._request(
            "POST", "tailor", json={"jobIds": job_ids, "deep": deep}
        ).json()

    def authoring_context(self, job_id: int) -> JSON:
        return self._request("GET", f"jobs/{_id(job_id)}/authoring-context").json()

    def validate_resume(
        self, job_id: int, content: JSON, *, context_revision: str
    ) -> JSON:
        return self._request(
            "POST",
            f"jobs/{_id(job_id)}/external-resume/validate",
            json={"content": content, "contextRevision": context_revision},
        ).json()

    def submit_resume(
        self,
        job_id: int,
        content: JSON,
        *,
        context_revision: str,
        agent: str = "external",
    ) -> JSON:
        return self._request(
            "POST",
            f"jobs/{_id(job_id)}/external-resume",
            json={
                "content": content,
                "contextRevision": context_revision,
                "agent": agent,
            },
        ).json()

    def get_run(self, run_id: str, *, timeout: float | None = None) -> JSON:
        return self._request(
            "GET",
            f"runs/{quote(run_id, safe='')}",
            timeout=self._timeout if timeout is None else timeout,
        ).json()

    def list_runs(self, *, page: int = 1, page_size: int = 100) -> JSON:
        """Active and recently completed runs in the server's visibility window."""
        return self._request(
            "GET", "runs", params={"page": page, "pageSize": page_size}
        ).json()

    def wait(
        self, run: JSON | str, *, timeout: float = 600, poll_interval: float = 1
    ) -> JSON:
        _positive(timeout, "timeout")
        _positive(poll_interval, "poll_interval")
        run_id = run if isinstance(run, str) else run["runId"]
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RunTimeout(run_id)
            state = self.get_run(run_id, timeout=min(self._timeout, remaining))
            if state["state"] == "done":
                return state
            if state["state"] in {"error", "cancelled"}:
                raise RunFailed(state)
            time.sleep(min(poll_interval, max(0, deadline - time.monotonic())))

    def cancel_run(self, run_id: str) -> JSON:
        return self._request("POST", f"runs/{quote(run_id, safe='')}/cancel").json()

    def render_resume(self, version_id: int) -> JSON:
        return self._request("POST", f"resume-versions/{_id(version_id)}/render").json()

    def get_resume(self, version_id: int) -> JSON:
        return self._request("GET", f"resume-versions/{_id(version_id)}/content").json()

    def download_resume(self, version_id: int) -> bytes:
        return self._request("GET", f"resume-versions/{_id(version_id)}/pdf").content
