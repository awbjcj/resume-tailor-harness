from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator, model_validator

from resume_tailor_harness.api.schemas.base import CamelModel


class EmailNotificationUpdate(CamelModel):
    email: EmailStr | Literal[""] = ""
    enabled: bool = False
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    pending_reviews: bool = True
    statistics: bool = True
    reminders: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()

    @model_validator(mode="after")
    def require_content(self):
        if self.enabled and not self.email:
            raise ValueError("An email address is required to opt in.")
        if self.enabled and not any(
            (self.pending_reviews, self.statistics, self.reminders)
        ):
            raise ValueError("Select at least one email topic.")
        return self


class EmailNotificationOut(EmailNotificationUpdate):
    verified_at: datetime | None = None
    verification_pending: bool = False
    next_send_at: datetime | None = None
    last_sent_at: datetime | None = None
    delivery_available: bool = False
    delivery_failed: bool = False


class NotificationVerification(CamelModel):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")
