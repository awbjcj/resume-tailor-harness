"""Validate provider data before it reaches storage or email analysis."""

from pydantic import AwareDatetime, BaseModel, Field


class TokenPayload(BaseModel):
    access_token: str = Field(min_length=1)
    refresh_token: str | None = Field(default=None, min_length=1)
    scope: str = ""
    expires_in: float = Field(default=3600, gt=0, allow_inf_nan=False)


class ProfilePayload(BaseModel):
    id: str = Field(min_length=1)
    mail: str | None = None
    userPrincipalName: str | None = None


class StoredMicrosoftToken(BaseModel):
    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    expires_at: float = Field(default=0, ge=0, allow_inf_nan=False)


class _Address(BaseModel):
    address: str | None = None


class _Sender(BaseModel):
    emailAddress: _Address | None = None


class _Body(BaseModel):
    content: str | None = None
    contentType: str | None = None


class MessagePayload(BaseModel):
    id: str = Field(min_length=1)
    removed: dict | None = Field(default=None, alias="@removed")
    isDraft: bool = False
    sender: _Sender | None = Field(default=None, alias="from")
    subject: str | None = None
    body: _Body | None = None
    bodyPreview: str | None = None
    receivedDateTime: AwareDatetime | None = None


class DeltaPayload(BaseModel):
    value: list[MessagePayload]
    next: str | None = Field(default=None, alias="@odata.nextLink", min_length=1)
    delta: str | None = Field(default=None, alias="@odata.deltaLink", min_length=1)
