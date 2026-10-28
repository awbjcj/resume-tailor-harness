"""Mailbox checkpoints and bounded message evidence in the tenant database."""

from datetime import datetime
from typing import Any, cast

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel

from resume_tailor_harness.tracking.tables import utcnow


class GmailSyncState(SQLModel, table=True):
    __tablename__ = cast(Any, "gmail_sync_state")

    account: str = Field(primary_key=True)
    cursors: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class GmailReceipt(SQLModel, table=True):
    __tablename__ = cast(Any, "gmail_receipts")
    __table_args__ = (
        Index("ix_gmail_receipt_revision", "account", "revision", "attempted_at"),
        Index(
            "ix_gmail_receipt_application", "account", "application_id", "internal_date"
        ),
    )

    account: str = Field(primary_key=True)
    message_id: str = Field(primary_key=True)
    # Only normalized metadata and at most BODY_CHAR_LIMIT characters, no MIME
    # attachments or authentication material. Retained for offline re-matching.
    email_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    revision: str = ""
    application_id: int | None = None  # derived cache, deliberately not a foreign key
    bound_application_id: int | None = None
    internal_date: int = 0
    label: str = "none"
    classification_version: str = ""
    outcome: str = "unmatched"
    attempted_at: datetime = Field(default_factory=utcnow)
