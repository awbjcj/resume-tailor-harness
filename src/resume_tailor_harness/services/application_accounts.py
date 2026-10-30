"""Encrypted, tenant-bound employer accounts for host-operated applications.

No employer traffic happens here. The host observes the page, fills it, and
reports an outcome. Save before registration so interruptions keep the password.
"""

from __future__ import annotations

import os
import re
import secrets
import string
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session

from resume_tailor_harness.api.schemas.application_accounts import (
    AccountAccess,
    AccountOutcome,
    AccountOut,
    AccountPolicyUpdate,
    AccountPrepare,
    AccountPreparedOut,
    AccountSave,
    AccountSecretOut,
    AccountUpdate,
    AccountVaultOut,
)
from resume_tailor_harness.services.agent_applications import require_application_job
from resume_tailor_harness.tracking.tables import Job

_MAX_VAULT_BYTES = 4 * 1024 * 1024


class AccountVaultError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


class _StoredAccount(AccountOut):
    password: str = Field(repr=False)


class _Vault(BaseModel):
    version: int = 1
    owner: str
    auto_register: bool = False
    revision: int = 0
    accounts: list[_StoredAccount] = Field(default_factory=list)


def login_origin(url: str) -> str:
    """Exact HTTPS origin, never a registrable-domain or substring match.

    The employer is an additional scope for shared ATS hosts. Reject ambiguous
    URL forms instead of trying to reconcile browser/server parser differences.
    This function performs no request and does not resolve DNS.
    """
    try:
        if any(ord(c) < 33 or ord(c) == 127 for c in url) or "\\" in url:
            raise ValueError
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or not re.fullmatch(r"[A-Za-z0-9.-]+", host)
            or "." not in host
            or host.endswith(".")
            or any(
                not label or label.startswith("-") or label.endswith("-")
                for label in host.split(".")
            )
        ):
            raise ValueError
    except ValueError:
        raise AccountVaultError(
            "INVALID_LOGIN_URL", "Use an unambiguous HTTPS login URL on port 443", 422
        ) from None
    return f"https://{host.lower()}"


def _company(value: str | None) -> str:
    normalized = " ".join((value or "").split()).casefold()
    if not normalized:
        raise AccountVaultError(
            "COMPANY_REQUIRED", "A verified employer name is required", 422
        )
    return normalized


def _username(value: str | None) -> str:
    username = (value or "").strip()
    if not username or any(ord(c) < 32 for c in username):
        raise AccountVaultError(
            "USERNAME_REQUIRED", "Choose the account email or username", 422
        )
    return username


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_password(length: int, symbols: str) -> str:
    if not 16 <= length <= 128 or any(c not in string.punctuation for c in symbols):
        raise AccountVaultError(
            "PASSWORD_POLICY", "Use 16–128 characters and ASCII punctuation", 422
        )
    groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
    if symbols:
        groups.append("".join(dict.fromkeys(symbols)))
    chars = [secrets.choice(group) for group in groups]
    alphabet = "".join(groups)
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _metadata(account: _StoredAccount) -> AccountOut:
    return AccountOut.model_validate(account.model_dump(exclude={"password"}))


class AccountVault:
    def __init__(self, root: Path, owner: str, keys: str):
        self.root, self.owner = root, owner
        self.path = root / "application-accounts.vault"
        self.cipher: MultiFernet | None = None
        if keys.strip():
            try:
                self.cipher = MultiFernet(
                    [Fernet(key.strip()) for key in keys.split(",")]
                )
            except (ValueError, TypeError):
                raise AccountVaultError(
                    "VAULT_UNAVAILABLE", "The password vault key is invalid", 503
                ) from None

    @contextmanager
    def _locked(self) -> Iterator[_Vault]:
        if self.cipher is None:
            raise AccountVaultError(
                "VAULT_UNAVAILABLE",
                "Configure APPLICATION_VAULT_KEYS to enable the password manager",
                503,
            )
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(".lock")
        if self.path.is_symlink() or lock_path.is_symlink():
            raise AccountVaultError(
                "VAULT_UNAVAILABLE", "Unsafe password vault path", 503
            )
        try:
            with FileLock(lock_path, timeout=10):
                yield self._read()
        except Timeout:
            raise AccountVaultError(
                "VAULT_BUSY",
                "Password vault is busy; read current state before retrying",
            ) from None

    def _read(self) -> _Vault:
        assert self.cipher is not None
        if not self.path.exists():
            return _Vault(owner=self.owner)
        try:
            if self.path.stat().st_size > _MAX_VAULT_BYTES:
                raise ValueError
            data = _Vault.model_validate_json(
                self.cipher.decrypt(self.path.read_bytes())
            )
            if data.owner != self.owner or data.version != 1:
                raise ValueError
            return data
        except (InvalidToken, ValueError, ValidationError):
            # Never replace an unreadable vault or echo any decrypted data.
            raise AccountVaultError(
                "VAULT_UNREADABLE",
                "Cannot unlock this workspace's password vault; check the key and backup",
                503,
            ) from None

    def _write(self, data: _Vault) -> None:
        assert self.cipher is not None
        # Entire document, including usernames and policy, is authenticated.
        encrypted = self.cipher.encrypt(data.model_dump_json().encode())
        if len(encrypted) > _MAX_VAULT_BYTES:
            raise AccountVaultError(
                "VAULT_FULL",
                "Password vault capacity reached; remove an unused account",
            )
        fd, name = tempfile.mkstemp(prefix=".application-accounts-", dir=self.root)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def status(self) -> AccountVaultOut:
        if self.cipher is None:
            return AccountVaultOut(configured=False)
        with self._locked() as data:
            return AccountVaultOut(
                configured=True,
                auto_register=data.auto_register,
                revision=data.revision,
                accounts=[_metadata(a) for a in data.accounts],
            )

    def policy(self, body: AccountPolicyUpdate) -> AccountVaultOut:
        with self._locked() as data:
            if body.revision != data.revision:
                raise AccountVaultError(
                    "VAULT_STALE",
                    "Read the password manager again before changing preferences",
                )
            data.auto_register = body.auto_register
            data.revision += 1
            self._write(data)
            return AccountVaultOut(
                configured=True,
                auto_register=data.auto_register,
                revision=data.revision,
                accounts=[_metadata(a) for a in data.accounts],
            )

    @staticmethod
    def _match(data: _Vault, company: str, origin: str) -> _StoredAccount | None:
        return next(
            (
                a
                for a in data.accounts
                if _company(a.company) == _company(company) and a.origin == origin
            ),
            None,
        )

    def _add(
        self,
        data: _Vault,
        company: str,
        origin: str,
        username: str,
        password: str,
        *,
        active: bool,
    ) -> _StoredAccount:
        if len(data.accounts) >= 1000:
            raise AccountVaultError(
                "VAULT_FULL", "Remove an unused account before adding another"
            )
        now = _now()
        account = _StoredAccount(
            id=str(uuid4()),
            company=company.strip(),
            origin=origin,
            username=_username(username),
            password=password,
            status="active" if active else "pending",
            revision=1,
            created_at=now,
            updated_at=now,
        )
        data.accounts.append(account)
        data.revision += 1
        self._write(data)
        return account

    def save(self, body: AccountSave) -> AccountOut:
        company, origin = _company(body.company), login_origin(body.login_url)
        with self._locked() as data:
            if self._match(data, company, origin):
                raise AccountVaultError(
                    "ACCOUNT_EXISTS",
                    "An account is already saved for this employer and login site",
                )
            return _metadata(
                self._add(
                    data,
                    body.company,
                    origin,
                    body.username,
                    body.password.get_secret_value(),
                    active=True,
                )
            )

    @staticmethod
    def _get(data: _Vault, account_id: str, revision: int) -> _StoredAccount:
        account = next((a for a in data.accounts if a.id == account_id), None)
        if account is None:
            raise AccountVaultError("NOT_FOUND", "Account not found", 404)
        if account.revision != revision:
            raise AccountVaultError(
                "ACCOUNT_STALE", "Read the account again before using or changing it"
            )
        return account

    def update(self, account_id: str, body: AccountUpdate) -> AccountOut:
        with self._locked() as data:
            account = self._get(data, account_id, body.revision)
            account.password = body.password.get_secret_value()
            account.status = "active"
            self._changed(data, account)
            return _metadata(account)

    def delete(self, account_id: str, revision: int) -> None:
        with self._locked() as data:
            account = self._get(data, account_id, revision)
            data.accounts.remove(account)
            data.revision += 1
            self._write(data)

    def _changed(self, data: _Vault, account: _StoredAccount) -> None:
        account.revision += 1
        account.updated_at = _now()
        data.revision += 1
        self._write(data)

    def prepare(
        self,
        session: Session,
        job_id: int,
        body: AccountPrepare,
        *,
        default_username: str,
    ) -> AccountPreparedOut:
        job = require_application_job(session, job_id)
        company, origin = _company(job.company), login_origin(body.browser_url)
        with self._locked() as data:
            account = self._match(data, company, origin)
            if account is not None:
                if account.status == "pending" and not data.auto_register:
                    raise AccountVaultError(
                        "REGISTRATION_DISABLED",
                        "Automatic account creation is disabled; preserve the unfinished registration",
                    )
                if (
                    body.username is not None
                    and _username(body.username) != account.username
                ):
                    raise AccountVaultError(
                        "ACCOUNT_USERNAME_MISMATCH",
                        "Use the saved username or manage this account in settings",
                    )
                action: Literal["login", "resume_registration", "needs_attention"] = (
                    "login"
                    if account.status == "active"
                    else "resume_registration"
                    if account.status == "pending"
                    else "needs_attention"
                )
                return AccountPreparedOut(action=action, account=_metadata(account))
            if not data.auto_register:
                raise AccountVaultError(
                    "REGISTRATION_DISABLED",
                    "Enable automatic account creation in Password manager or save an existing account",
                )
            if not job.url or login_origin(job.url) != origin:
                raise AccountVaultError(
                    "LOGIN_SITE_UNTRUSTED",
                    "The login site differs from the job site; confirm it with the user and save the account in settings",
                )
            password = generate_password(body.password_length, body.password_symbols)
            account = self._add(
                data,
                job.company or company,
                origin,
                _username(body.username or default_username),
                password,
                active=False,
            )
            return AccountPreparedOut(action="register", account=_metadata(account))

    def _for_job(
        self, data: _Vault, job: Job, account_id: str, body: AccountAccess
    ) -> _StoredAccount:
        account = self._get(data, account_id, body.revision)
        if (
            _company(job.company) != _company(account.company)
            or login_origin(body.browser_url) != account.origin
        ):
            raise AccountVaultError(
                "ACCOUNT_SCOPE_MISMATCH",
                "Account does not match the employer and current HTTPS login site",
                403,
            )
        return account

    def secret(
        self, session: Session, job_id: int, account_id: str, body: AccountAccess
    ) -> AccountSecretOut:
        job = require_application_job(session, job_id)
        with self._locked() as data:
            account = self._for_job(data, job, account_id, body)
            if account.status == "pending" and not data.auto_register:
                raise AccountVaultError(
                    "REGISTRATION_DISABLED", "Automatic account creation is disabled"
                )
            if account.status == "needs_attention":
                raise AccountVaultError(
                    "ACCOUNT_NEEDS_ATTENTION",
                    "Repair the saved account before trying another login",
                )
            return AccountSecretOut(
                account=_metadata(account), password=account.password
            )

    def outcome(
        self, session: Session, job_id: int, account_id: str, body: AccountOutcome
    ) -> AccountOut:
        job = require_application_job(session, job_id)
        with self._locked() as data:
            account = self._for_job(data, job, account_id, body)
            if body.outcome == "authenticated":
                account.status = "active"
                account.last_used_at = _now()
            elif body.outcome == "failed":
                account.status = "needs_attention"
            # Verification is not evidence of authentication; preserve status.
            self._changed(data, account)
            return _metadata(account)
