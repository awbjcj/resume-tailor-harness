"""Tenant database records for review, receipts and versioned notes."""

from datetime import datetime
from typing import Any, cast

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from resume_tailor_harness.tracking.tables import utcnow


class WorkspaceProposal(SQLModel, table=True):
    __tablename__ = cast(Any, "workspace_proposals")

    id: str = Field(primary_key=True)
    surface: str = Field(index=True)
    session_id: str = Field(index=True)
    run_id: str = ""
    title: str
    digest: str
    actions: list[dict[str, Any]] = Field(sa_column=Column(JSON))
    source_text: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime


class WorkspaceActionReceipt(SQLModel, table=True):
    __tablename__ = cast(Any, "workspace_action_receipts")

    id: str = Field(primary_key=True)
    proposal_id: str = Field(foreign_key="workspace_proposals.id", index=True)
    state: str = "applied"
    approved_by: str
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class WorkspaceNote(SQLModel, table=True):
    __tablename__ = cast(Any, "workspace_notes")

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    kind: str = "note"
    title: str
    body: str
    revision: int = 1
    deleted: bool = False
    citations: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
