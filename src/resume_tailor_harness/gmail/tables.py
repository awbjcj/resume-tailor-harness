"""Mailbox checkpoints and bounded message evidence in the tenant database."""

from datetime import datetime
from typing import Any, cast

from sqlalchemy import JSON, Column, Index
from sqlalchemy.engine import Engine
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
        Index("ix_gmail_receipt_global_application", "application_id", "internal_date"),
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
    # Fingerprint of completed classifier input/version/mode, including "none".
    classification_version: str = ""
    outcome: str = "unmatched"
    attempted_at: datetime = Field(default_factory=utcnow)


def ensure_cross_account_index(engine: Engine) -> None:
    """create_all does not add indexes to existing tables on workspace upgrades."""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_gmail_receipt_global_application "
            "ON gmail_receipts (application_id, internal_date)"
        )
