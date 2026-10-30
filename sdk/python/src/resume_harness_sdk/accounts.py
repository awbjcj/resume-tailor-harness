"""Metadata contracts and a host-controlled password-field adapter.

The adapter runs in the trusted browser/computer runtime. Its callbacks must not
log their arguments or return field values to a model. It never clicks Submit.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, TypeAdapter
from typing_extensions import TypedDict


class ApplicationAccount(TypedDict):
    id: str
    company: str
    origin: str
    username: str
    status: Literal["pending", "active", "needs_attention"]
    revision: int
    createdAt: str
    updatedAt: str
    lastUsedAt: str | None


class AccountVault(TypedDict):
    configured: bool
    autoRegister: bool
    revision: int
    accounts: list[ApplicationAccount]


class PreparedAccount(TypedDict):
    action: Literal["register", "login", "resume_registration", "needs_attention"]
    account: ApplicationAccount


class _SecretPayload(BaseModel):
    account: ApplicationAccount
    password: SecretStr = Field(repr=False)


ACCOUNT = TypeAdapter(ApplicationAccount)
VAULT = TypeAdapter(AccountVault)
PREPARED = TypeAdapter(PreparedAccount)


def _origin(url: str) -> str:
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 443)
            or "\\" in url
            or any(ord(c) < 33 or ord(c) == 127 for c in url)
        ):
            raise ValueError
        return f"https://{parts.hostname.lower()}"
    except ValueError:
        raise ValueError(
            "The password form must be on an unambiguous HTTPS origin"
        ) from None


@dataclass(frozen=True)
class PasswordForm:
    """Bind callbacks to one verified page/frame, never a global active tab.

    ``current_url`` must read the actual target frame's URL each time.
    ``is_password`` verifies a visible editable input of type=password.
    ``fill`` replaces a field value without logging it, submitting, or navigation.
    The host owns locator validation, browser permissions, and account consent.
    """

    current_url: Callable[[], str] = field(repr=False)
    is_password: Callable[[str], bool] = field(repr=False)
    fill: Callable[[str, str], None] = field(repr=False)
    username_selector: str
    password_selector: str
    confirmation_selector: str | None = None

    def check(self, expected_origin: str) -> None:
        if _origin(self.current_url()) != expected_origin:
            raise ValueError("Password form navigated to a different login origin")
        selectors = [self.username_selector, self.password_selector]
        if self.confirmation_selector:
            selectors.append(self.confirmation_selector)
        if any(not s.strip() for s in selectors) or len(set(selectors)) != len(
            selectors
        ):
            raise ValueError("Use distinct, nonempty username and password fields")
        if not self.is_password(self.password_selector) or (
            self.confirmation_selector
            and not self.is_password(self.confirmation_selector)
        ):
            raise ValueError(
                "Refusing to fill a secret outside a verified password field"
            )

    def apply(self, account: ApplicationAccount, password: SecretStr) -> None:
        try:
            self.check(account["origin"])
            self.fill(self.username_selector, account["username"])
            self.check(account["origin"])
            self.fill(self.password_selector, password.get_secret_value())
            if self.confirmation_selector:
                self.check(account["origin"])
                self.fill(self.confirmation_selector, password.get_secret_value())
        except Exception:
            # Browser exceptions may echo fill arguments. Do not chain them.
            raise RuntimeError(
                "Account fill stopped; inspect the page before retrying"
            ) from None
