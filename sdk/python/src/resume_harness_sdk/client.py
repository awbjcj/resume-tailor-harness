from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import Any, Literal
from urllib.parse import quote

from pydantic import ValidationError

from . import accounts
from ._applications import ApplicationAPI
from ._operations import OperationAPI
from ._transport import (
    APIError as APIError,
    JSON,
    ResponseValidationError,
    RunFailed,
    RunTimeout,
    _id,
    _positive,
    _validated,
)


class ResumeHarness(ApplicationAPI, OperationAPI):
    """Synchronous API client. Responses preserve the API's JSON field names.

    base_url is the deployment origin (optionally ending in /api). API keys are
    personal access tokens, not an OpenAI/Anthropic key. Writes are never retried.
    """

    @classmethod
    def from_env(cls, **kwargs) -> ResumeHarness:
        """Read RESUME_HARNESS_URL and RESUME_HARNESS_API_KEY."""
        return cls(
            base_url=os.environ["RESUME_HARNESS_URL"],
            api_key=os.environ["RESUME_HARNESS_API_KEY"],
            **kwargs,
        )

    def list_application_accounts(self) -> accounts.AccountVault:
        return _validated(self._request("GET", "application-accounts"), accounts.VAULT)

    def prepare_application_account(
        self,
        job_id: int,
        *,
        browser_url: str,
        username: str | None = None,
        password_length: int = 24,
        password_symbols: str = "!@#$%*-_",
    ) -> accounts.PreparedAccount:
        """Save/reuse an account, returning metadata only. No browser action."""
        body: JSON = {
            "browserUrl": browser_url,
            "passwordLength": password_length,
            "passwordSymbols": password_symbols,
        }
        if username is not None:
            body["username"] = username
        return _validated(
            self._request(
                "POST", f"jobs/{_id(job_id)}/application-account/prepare", json=body
            ),
            accounts.PREPARED,
        )

    def fill_application_account(
        self,
        job_id: int,
        account: accounts.ApplicationAccount,
        *,
        form: accounts.PasswordForm,
    ) -> accounts.ApplicationAccount:
        """Fill in the trusted host runtime; return metadata, never the password.

        A browser integration must bind PasswordForm to verified locators on a
        single page/frame. No secret-printing CLI command is provided.
        """
        form.check(account["origin"])
        response = self._request(
            "POST",
            f"jobs/{_id(job_id)}/application-accounts/{quote(account['id'], safe='')}/secret",
            json={"browserUrl": form.current_url(), "revision": account["revision"]},
        )
        try:
            payload = accounts._SecretPayload.model_validate_json(response.content)
        except (ValueError, ValidationError):
            raise ResponseValidationError("Invalid password-manager response") from None
        if payload.account != account:
            raise ResponseValidationError(
                "Password-manager account changed; prepare again"
            )
        form.apply(payload.account, payload.password)
        return payload.account

    def record_application_account_outcome(
        self,
        job_id: int,
        account: accounts.ApplicationAccount,
        *,
        browser_url: str,
        outcome: Literal["authenticated", "verification_required", "failed"],
    ) -> accounts.ApplicationAccount:
        """Record an observed site outcome; a click alone is not authentication."""
        return _validated(
            self._request(
                "POST",
                f"jobs/{_id(job_id)}/application-accounts/{quote(account['id'], safe='')}/outcome",
                json={
                    "browserUrl": browser_url,
                    "revision": account["revision"],
                    "outcome": outcome,
                },
            ),
            accounts.ACCOUNT,
        )

    def __enter__(self) -> ResumeHarness:
        return self

    def __exit__(self, *args) -> None:
        self.close()

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
        return self.create_job({**metadata, "jdText": jd_text})

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
