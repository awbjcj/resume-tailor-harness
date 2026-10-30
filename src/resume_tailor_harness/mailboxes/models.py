from __future__ import annotations

import re
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, field_validator

from resume_tailor_harness.api.schemas.base import CamelModel


class MailboxError(Exception):
    code = "MAILBOX_ERROR"
    status_code = 503

    def __init__(self, message: str = "", *, fields: tuple[str, ...] = ()):
        super().__init__(message)
        self.details = [
            {"loc": ["body", *field.split(".")], "type": self.code} for field in fields
        ] or None


class MailboxBusy(MailboxError):
    code = "MAILBOX_BUSY"
    status_code = 409


class MailboxLimit(MailboxError):
    code = "MAILBOX_LIMIT"
    status_code = 409


class MailboxCredentials(MailboxError):
    code = "MAILBOX_CREDENTIALS"
    status_code = 422


class MailboxFolder(MailboxError):
    code = "MAILBOX_FOLDER"
    status_code = 422


class MailboxProviderResponse(MailboxError):
    code = "MAILBOX_PROVIDER_RESPONSE"
    status_code = 502


class MailServer(CamelModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    security: Literal["tls", "starttls"] = "tls"
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator("host")
    @classmethod
    def hostname(cls, value: str) -> str:
        value = value.strip().lower().rstrip(".")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value):
            raise ValueError("Enter a server hostname without a scheme, path, or port")
        return value

    @field_validator("username")
    @classmethod
    def safe_username(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid username")
        return value.strip()


class MailboxConnectIn(CamelModel):
    provider: Literal["yahoo", "icloud", "fastmail", "custom"] = "custom"
    email: EmailStr
    imap: MailServer
    smtp: MailServer | None = None
    folder: str = Field(default="INBOX", min_length=1, max_length=200)

    @field_validator("folder")
    @classmethod
    def safe_folder(cls, value: str) -> str:
        if any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise ValueError("Use the folder's IMAP ASCII name")
        return value


class MailboxOut(CamelModel):
    id: str
    provider: str
    email: str
    folder: str = "INBOX"
    smtp_configured: bool = False
    needs_reconnect: bool = False


class MailProviderOut(CamelModel):
    id: str
    name: str
    auth: Literal["oauth", "password"]
    available: bool = True
    imap_host: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_security: Literal["tls", "starttls"] = "tls"
    help_url: str = ""


class MailboxesOut(CamelModel):
    providers: list[MailProviderOut]
    accounts: list[MailboxOut]


class MailboxAuthOut(CamelModel):
    auth_url: str
