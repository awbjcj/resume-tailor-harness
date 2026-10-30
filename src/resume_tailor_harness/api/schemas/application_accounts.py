"""Password-manager contracts. Ordinary responses contain metadata only."""

from typing import Literal

from pydantic import ConfigDict, Field, SecretStr

from .base import CamelModel


class AccountInput(CamelModel):
    model_config = ConfigDict(extra="forbid")


class AccountOut(CamelModel):
    id: str
    company: str
    origin: str
    username: str
    status: Literal["pending", "active", "needs_attention"]
    revision: int
    created_at: str
    updated_at: str
    last_used_at: str | None = None


class AccountVaultOut(CamelModel):
    configured: bool
    auto_register: bool = False
    revision: int = 0
    accounts: list[AccountOut] = Field(default_factory=list)


class AccountPolicyUpdate(AccountInput):
    auto_register: bool
    revision: int = Field(ge=0)
    user_confirmed: Literal[True]


class AccountSave(AccountInput):
    company: str = Field(min_length=1, max_length=200)
    login_url: str = Field(min_length=1, max_length=2048)
    username: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)
    user_confirmed: Literal[True]


class AccountUpdate(AccountInput):
    password: SecretStr = Field(min_length=1, max_length=1024)
    revision: int = Field(ge=1)
    user_confirmed: Literal[True]


class AccountPrepare(AccountInput):
    browser_url: str = Field(min_length=1, max_length=2048)
    # Used only for a new account. Never silently change an existing username.
    username: str | None = Field(default=None, min_length=1, max_length=320)
    password_length: int = Field(default=24, ge=16, le=128)
    password_symbols: str = Field(default="!@#$%*-_", max_length=32)


class AccountAccess(AccountInput):
    browser_url: str = Field(min_length=1, max_length=2048)
    revision: int = Field(ge=1)


class AccountOutcome(AccountAccess):
    outcome: Literal["authenticated", "verification_required", "failed"]


class AccountPreparedOut(CamelModel):
    action: Literal["register", "login", "resume_registration", "needs_attention"]
    account: AccountOut


class AccountSecretOut(CamelModel):
    """Dedicated secret transport; never embed in a context or ordinary response."""

    account: AccountOut
    password: str = Field(repr=False)
