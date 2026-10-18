"""Stable handoff and personal-answer contracts for external agent harnesses."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, StringConstraints, model_validator

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.api.schemas.config import ApplicationProfileDoc

QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class StrictInput(CamelModel):
    model_config = ConfigDict(extra="forbid")


class ApplicationProfilePatch(ApplicationProfileDoc):
    """Use only explicitly supplied fields; empty strings clear an answer."""

    model_config = ConfigDict(extra="forbid")


class ConfirmedInput(StrictInput):
    user_confirmed: StrictBool

    @model_validator(mode="after")
    def require_confirmation(self) -> Self:
        if not self.user_confirmed:
            raise ValueError("Only user-confirmed answers may be saved")
        return self


class ApplicationProfileUpdate(ConfirmedInput):
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile: ApplicationProfilePatch


class ApplicationProfileOut(CamelModel):
    profile: ApplicationProfileDoc
    revision: str


class ApplicationQuestionCreate(StrictInput):
    question: QuestionText
    context: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=4000)
    ] = ""
    scope: Literal["job", "profile"] = "job"
    job_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if (self.scope == "job") != (self.job_id is not None):
            raise ValueError("job scope requires jobId; profile scope must omit jobId")
        return self


class ApplicationQuestionUpdate(ConfirmedInput):
    revision: int = Field(ge=1)
    answer: QuestionText | None


class ApplicationQuestionOut(CamelModel):
    id: int
    question: str
    context: str
    scope: Literal["job", "profile"]
    job_id: int | None
    answer: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class ApplicationJobOut(CamelModel):
    job_id: int
    title: str | None
    company: str | None
    location: str | None
    url: str | None
    status: str


class ApplicationJobContext(ApplicationJobOut):
    jd_text: str


class ApplicationAttachmentOut(CamelModel):
    id: int
    kind: Literal["resume", "cover_letter"]
    is_selected: bool
    download_path: str | None


class ApplicationContextOut(CamelModel):
    job: ApplicationJobContext
    prompt: str
    profile: ApplicationProfileDoc
    profile_revision: str
    questions: list[ApplicationQuestionOut]
    attachments: list[ApplicationAttachmentOut]
    submission_policy: Literal["stop_before_submit"] = "stop_before_submit"
