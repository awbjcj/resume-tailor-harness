"""Application preparation and confirmed-answer writes."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Literal

from . import applications
from ._transport import JSON, _Transport, _id, _validated


class ApplicationAPI(_Transport):
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

    def get_application_prompt(self, job_id: int) -> applications.ApplicationPrompt:
        """Read the clipboard handoff for any existing job, including materials.

        Unlike application_context, this read does not assert queue eligibility.
        It must never be used to bypass an archived or submitted application.
        """
        return _validated(
            self._request("GET", f"jobs/{_id(job_id)}/application-prompt"),
            applications.PROMPT,
        )

    def get_application_materials(
        self, job_id: int
    ) -> applications.ApplicationMaterials | None:
        """Read exact selections and eligibility; None means an older server.

        Missing PDFs, blocked selections and absent material metadata are distinct
        states. This read never chooses documents or creates tracking records.
        """
        return self.get_application_prompt(job_id).get("materials")

    def application_next_step(
        self, job_id: int
    ) -> applications.ApplicationNextStep | None:
        """Read the server's current next work; None may mean an older server."""
        detail = _validated(
            self._request("GET", f"jobs/{_id(job_id)}"), applications.CONTINUATION
        )
        return detail.get("nextStep")

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

    def deselect_resume(self, job_id: int) -> applications.ApplicationRecord:
        """Clear an explicit choice when requested; the stored document is kept."""
        return _validated(
            self._request("DELETE", f"jobs/{_id(job_id)}/select-resume"),
            applications.APPLICATION,
        )

    def deselect_cover_letter(self, job_id: int) -> applications.ApplicationRecord:
        """Clear a letter choice without deleting the letter or recording submission."""
        return _validated(
            self._request("DELETE", f"jobs/{_id(job_id)}/select-cover-letter"),
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
        self,
        job_id: int,
        event: applications.ApplicationEventCreate | Mapping[str, Any],
    ) -> applications.ApplicationEvent:
        """Record an observed event using API camelCase fields.

        application_submitted requires occurredAt with a UTC offset and advances
        tracking to submitted. Only record it after verified employer submission.
        This POST is not idempotent; inspect history after an ambiguous failure.
        """
        return _validated(
            self._request("POST", f"jobs/{_id(job_id)}/events", json=dict(event)),
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
        return self.patch_application_profile(
            {"profile": changes, "revision": revision, "userConfirmed": user_confirmed}
        )

    def patch_application_profile(
        self, body: applications.ApplicationProfileUpdate | Mapping[str, Any]
    ) -> applications.ApplicationProfileSnapshot:
        """Send a complete PATCH envelope, including unknown keys for validation.

        Only confirmed supplied fields are changed. Reconcile PROFILE_STALE
        before retrying; lists replace in full and nested names/addresses merge.
        """
        return _validated(
            self._request(
                "PATCH",
                "application-profile",
                json=dict(body),
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
        return self.create_application_question(
            {"question": question, "context": context, "scope": scope, "jobId": job_id}
        )

    def create_application_question(
        self, body: applications.ApplicationQuestionCreate | Mapping[str, Any]
    ) -> applications.ApplicationQuestion:
        """Send an exact, repeat-safe question-create envelope for server validation."""
        return _validated(
            self._request(
                "POST",
                "application-questions",
                json=dict(body),
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
        return self.update_application_question(
            question_id,
            {"answer": answer, "revision": revision, "userConfirmed": user_confirmed},
        )

    def update_application_question(
        self,
        question_id: int,
        body: applications.ApplicationQuestionUpdate | Mapping[str, Any],
    ) -> applications.ApplicationQuestion:
        """Send a revision-protected confirmed answer; None explicitly clears it."""
        return _validated(
            self._request(
                "PATCH",
                f"application-questions/{_id(question_id)}",
                json=dict(body),
            ),
            applications.QUESTION,
        )

    def get_application_question(
        self, question_id: int
    ) -> applications.ApplicationQuestion:
        return _validated(
            self._request("GET", f"application-questions/{_id(question_id)}"),
            applications.QUESTION,
        )
