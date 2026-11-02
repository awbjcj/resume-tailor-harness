from __future__ import annotations

from datetime import datetime

from pydantic import model_validator

from resume_tailor_harness.api.schemas.application_events import ApplicationEventCreate
from resume_tailor_harness.api.schemas.base import CamelModel


class NotificationAcceptIn(CamelModel):
    event: ApplicationEventCreate | None = None
    expected_revision: str | None = None
    event_details_confirmed: bool = False

    @model_validator(mode="after")
    def require_event_review(self) -> NotificationAcceptIn:
        if self.event is not None and (
            not self.expected_revision or not self.event_details_confirmed
        ):
            raise ValueError(
                "Timeline capture requires the reviewed proposal revision and "
                "confirmation of the event details"
            )
        return self


class NotificationOut(CamelModel):
    id: int
    application_id: int
    kind: str
    proposed_status: str
    evidence: str
    message_id: str
    state: str
    created_at: datetime
    revision: str
    job_id: int | None = None
    company: str | None = None
    title: str | None = None
