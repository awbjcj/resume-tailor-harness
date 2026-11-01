"""Closed model-facing commands. Approval is deliberately not a model field."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Surface = Literal["coach", "career-lab", "interview", "scout"]
Operation = Literal[
    "job.create",
    "job.update",
    "job.archive",
    "job.restore",
    "job.delete",
    "application.update",
    "event.create",
    "event.update",
    "event.delete",
    "note.create",
    "note.update",
    "note.delete",
    "preparation.save",
    "profile.change",
    "application_profile.update",
    "question.create",
    "question.update",
    "question.delete",
    "artifact.select",
    "artifact.delete",
    "search.update",
]


class WorkspaceChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Operation
    job_id: int | None = Field(default=None, ge=1)
    target_id: int | None = Field(default=None, ge=1)
    values: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=1000)
    citations: list[str] = Field(default_factory=list, max_length=20)


class WorkspacePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    changes: list[WorkspaceChange] = Field(min_length=1, max_length=20)
