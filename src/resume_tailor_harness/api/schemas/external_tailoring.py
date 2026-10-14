"""The external-author contract uses native snake_case inside domain JSON."""

from typing import Any

from pydantic import Field

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.models.resume import ResumeContent


class AuthoringContextOut(CamelModel):
    job_id: int
    company: str | None
    title: str | None
    jd_text: str
    context_revision: str
    profile: dict[str, Any]
    resume_schema: dict[str, Any]
    length_budget: dict[str, Any]
    style_guide: str | None


class ExternalDraftIn(CamelModel):
    content: ResumeContent
    context_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    agent: str = Field(default="external", min_length=1, max_length=100)


class DraftValidationOut(CamelModel):
    valid: bool
    context_revision: str
    critiques: list[dict[str, Any]]
