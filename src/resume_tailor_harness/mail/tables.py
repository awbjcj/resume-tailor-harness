"""Workspace-owned consent, verification and durable digest delivery state."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class EmailNotificationPreference(SQLModel, table=True):
    # One recipient per isolated workspace. Never exported in settings bundles.
    id: int = Field(default=1, primary_key=True)
    email: str = ""
    enabled: bool = False
    frequency: str = "weekly"
    pending_reviews: bool = True
    statistics: bool = True
    reminders: bool = True
    verified_at: datetime | None = None
    code_hash: str = ""
    expires_at: datetime | None = None
    attempts: int = 0
    code_sent_at: datetime | None = None
    send_window_at: datetime | None = None
    send_count: int = 0
    unsubscribe_token: str = ""
    next_send_at: datetime | None = None
    last_sent_at: datetime | None = None
    retry_at: datetime | None = None
    delivery_failures: int = 0
    # Persist the exact request before delivery, so retries have identical content.
    pending_payload: str = ""
    pending_since: datetime | None = None
