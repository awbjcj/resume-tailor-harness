from __future__ import annotations

import math
import os
import time
from collections.abc import Iterator
from typing import Any, Literal, TypeVar, cast
from urllib.parse import quote, urlsplit

import httpx
from pydantic import TypeAdapter, ValidationError

from . import applications

JSON = dict[str, Any]
T = TypeVar("T")


class ResponseValidationError(RuntimeError):
    """The server response does not match the SDK's application contract."""


def _validated(response: httpx.Response, adapter: TypeAdapter[T]) -> T:
    try:
        payload = response.json()
        adapter.validate_python(payload, strict=True)
    except (ValueError, ValidationError):
        # Do not include personal data or an untrusted response in diagnostics.
        raise ResponseValidationError("Invalid application API response") from None
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
                "User-Agent": "resume-harness-sdk/0.3.0",
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

    def approve_job(self, job_id: int) -> JSON:
        """Move a chosen job to approved when the user authorizes preparation.

        Inspect get_job first; do not reset a tailored/rendered job's stage.
        Approval alone does not authorize employer submission.
        """
        return self._request(
            "PATCH", f"jobs/{_id(job_id)}", json={"status": "approved"}
        ).json()

    def list_application_jobs(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> applications.Page[applications.ApplicationJob]:
        return _validated(
            self._request(
                "GET",
                "application-jobs",
                params={"page": page, "pageSize": page_size},
            ),
            applications.JOBS,
        )

    def iter_application_jobs(
        self,
        *,
        page_size: int = 50,
    ) -> Iterator[applications.ApplicationJob]:
        page = 1
        while True:
            result = self.list_application_jobs(page=page, page_size=page_size)
            yield from result["data"]
            if not result["data"] or page >= result["pagination"]["totalPages"]:
                return
            page += 1

    def application_context(self, job_id: int) -> applications.ApplicationContext:
        return _validated(
            self._request(
                "GET",
                f"jobs/{_id(job_id)}/application-context",
            ),
            applications.CONTEXT,
        )

    def application_prompt(self, job_id: int) -> str:
        """Complete readable prompt including the JD, personal facts, and questions."""
        return self.application_context(job_id)["prompt"]

    def select_resume(
        self, job_id: int, version_id: int
    ) -> applications.ApplicationRecord:
        """Remember the resume chosen from this job's fresh eligible attachments.

        Selection creates/updates tracking only; it does not upload or submit.
        """
        return _validated(
            self._request(
                "POST", f"jobs/{_id(job_id)}/select-resume/{_id(version_id)}"
            ),
            applications.APPLICATION,
        )

    def select_cover_letter(
        self, job_id: int, cover_letter_id: int
    ) -> applications.ApplicationRecord:
        """Remember the cover letter chosen from eligible application attachments."""
        return _validated(
            self._request(
                "POST", f"jobs/{_id(job_id)}/select-cover-letter/{_id(cover_letter_id)}"
            ),
            applications.APPLICATION,
        )

    def list_application_events(
        self, job_id: int
    ) -> list[applications.ApplicationEvent]:
        """Read timeline history, including evidence of an earlier submission."""
        return _validated(
            self._request("GET", f"jobs/{_id(job_id)}/events"), applications.EVENTS
        )

    def record_application_event(
        self, job_id: int, event: JSON
    ) -> applications.ApplicationEvent:
        """Record an observed event using API camelCase fields.

        application_submitted requires occurredAt with a UTC offset and advances
        tracking to submitted. Only record it after verified employer submission.
        This POST is not idempotent; inspect history after an ambiguous failure.
        """
        return _validated(
            self._request("POST", f"jobs/{_id(job_id)}/events", json=event),
            applications.EVENT,
        )

    def get_application_profile(self) -> applications.ApplicationProfileSnapshot:
        return _validated(
            self._request("GET", "application-profile"), applications.PROFILE
        )

    def update_application_profile(
        self,
        changes: applications.ApplicationProfile,
        *,
        revision: str,
        user_confirmed: bool,
    ) -> applications.ApplicationProfileSnapshot:
        return _validated(
            self._request(
                "PATCH",
                "application-profile",
                json={
                    "profile": changes,
                    "revision": revision,
                    "userConfirmed": user_confirmed,
                },
            ),
            applications.PROFILE,
        )

    def list_application_questions(
        self,
        *,
        job_id: int | None = None,
        status: Literal["unanswered", "answered"] | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> applications.Page[applications.ApplicationQuestion]:
        params: JSON = {"page": page, "pageSize": page_size}
        if job_id is not None:
            params["jobId"] = _id(job_id)
        if status is not None:
            params["status"] = status
        return _validated(
            self._request("GET", "application-questions", params=params),
            applications.QUESTIONS,
        )

    def iter_application_questions(
        self,
        *,
        job_id: int | None = None,
        status: Literal["unanswered", "answered"] | None = None,
        page_size: int = 50,
    ) -> Iterator[applications.ApplicationQuestion]:
        page = 1
        while True:
            result = self.list_application_questions(
                job_id=job_id, status=status, page=page, page_size=page_size
            )
            yield from result["data"]
            if not result["data"] or page >= result["pagination"]["totalPages"]:
                return
            page += 1

    def record_application_question(
        self,
        question: str,
        *,
        job_id: int | None = None,
        scope: Literal["job", "profile"] = "job",
        context: str = "",
    ) -> applications.ApplicationQuestion:
        if job_id is not None:
            _id(job_id)
        return _validated(
            self._request(
                "POST",
                "application-questions",
                json={
                    "question": question,
                    "context": context,
                    "scope": scope,
                    "jobId": job_id,
                },
            ),
            applications.QUESTION,
        )

    def answer_application_question(
        self,
        question_id: int,
        answer: str | None,
        *,
        revision: int,
        user_confirmed: bool,
    ) -> applications.ApplicationQuestion:
        return _validated(
            self._request(
                "PATCH",
                f"application-questions/{_id(question_id)}",
                json={
                    "answer": answer,
                    "revision": revision,
                    "userConfirmed": user_confirmed,
                },
            ),
            applications.QUESTION,
        )

    def list_sources(self) -> Any:
        return self._request("GET", "sources").json()

    def get_application_question(
        self, question_id: int
    ) -> applications.ApplicationQuestion:
        return _validated(
            self._request("GET", f"application-questions/{_id(question_id)}"),
            applications.QUESTION,
        )

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

    def generate_cover_letters(self, job_ids: list[int]) -> JSON:
        """Start hosted cover-letter writing, fact checking, and PDF rendering."""
        if not job_ids:
            raise ValueError("Provide at least one job ID")
        for job_id in job_ids:
            _id(job_id)
        return self._request(
            "POST", "cover-letters", json={"jobIds": job_ids, "approved": False}
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

    def download_cover_letter(self, cover_letter_id: int) -> bytes:
        return self._request("GET", f"cover-letters/{_id(cover_letter_id)}/pdf").content
