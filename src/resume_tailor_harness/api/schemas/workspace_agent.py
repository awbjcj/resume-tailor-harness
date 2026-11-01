"""Browser review API contracts; embedded domain commands retain snake_case."""

from typing import Any, Literal

from pydantic import ConfigDict, Field

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.workspace_agent.models import Surface, WorkspaceChange


class ReceiptOut(CamelModel):
    state: str
    result: dict[str, Any]
    approved_by: str
    created_at: str


class ActionOut(CamelModel):
    id: str
    change: WorkspaceChange
    before: Any
    after: Any
    receipt: ReceiptOut | None = None


class ProposalOut(CamelModel):
    id: str
    title: str
    digest: str
    surface: Surface
    session_id: str
    created_at: str
    expires_at: str
    actions: list[ActionOut]


class ProposalPage(CamelModel):
    proposals: list[ProposalOut]
    next_offset: int | None = None


class ReviewIn(CamelModel):
    model_config = ConfigDict(extra="forbid")
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    action_ids: list[str] = Field(min_length=1, max_length=20)
    decision: Literal["apply", "discard"]
