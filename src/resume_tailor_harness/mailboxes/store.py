"""Tenant-owned secrets; atomic writes and one cross-process connection lock.

Like Gmail tokens and secrets.env, this private file is part of a full workspace
backup, never a settings bundle. Public projections never include credentials.
"""

import json
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

from filelock import FileLock, Timeout

from resume_tailor_harness.gmail.auth import token_path
from resume_tailor_harness.mailboxes.microsoft_payloads import StoredMicrosoftToken
from resume_tailor_harness.mailboxes.models import (
    MailboxConnectIn,
    MailboxBusy,
    MailboxError,
    MailboxLimit,
    MailboxOut,
)
from resume_tailor_harness.progress import atomic_write_text

FILENAME = "mailbox_connections.json"


def connections_path(data_dir: Path | None = None) -> Path:
    return token_path(data_dir).with_name(FILENAME)


@contextmanager
def connection_lock(data_dir: Path | None = None):
    path = connections_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.with_suffix(".lock").is_symlink():
        raise MailboxError("Unsafe mailbox storage path.")
    try:
        with FileLock(str(path.with_suffix(".lock")), timeout=0):
            yield
    except Timeout as exc:
        raise MailboxBusy(
            "A mailbox operation is already running. Try again shortly."
        ) from exc


def read_accounts(data_dir: Path | None = None) -> dict[str, dict]:
    path = connections_path(data_dir)
    if not path.exists():
        return {}
    try:
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise ValueError("Unsafe mailbox file")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or len(data) > 10:
            raise ValueError("Invalid mailbox file")
        for key, account in data.items():
            if account["id"] != key:
                raise ValueError("Invalid mailbox identity")
            public_account(account)
            if account["provider"] == "microsoft":
                token = account["token"]
                validated = StoredMicrosoftToken.model_validate(token)
                account["token"] = {**token, **validated.model_dump()}
            else:
                MailboxConnectIn.model_validate(account)
        return data
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise MailboxError(
            "Mailbox connections could not be read. Restore a valid backup."
        ) from exc


def write_accounts(accounts: dict[str, dict], data_dir: Path | None = None) -> None:
    path = connections_path(data_dir)
    if not accounts:
        path.unlink(missing_ok=True)
        return
    atomic_write_text(path, json.dumps(accounts), root=path.parent)
    path.chmod(0o600)


def account_id(*parts: str) -> str:
    return sha256(json.dumps(parts).encode()).hexdigest()


def public_account(account: dict) -> MailboxOut:
    return MailboxOut(
        id=account["id"],
        provider=account["provider"],
        email=account["email"],
        folder=account.get("folder", "INBOX"),
        smtp_configured=bool(account.get("smtp")),
        needs_reconnect=bool(account.get("needs_reconnect")),
    )


def save_account(account: dict, data_dir: Path | None = None) -> MailboxOut:
    # Caller owns connection_lock, also held throughout verification / sync.
    accounts = read_accounts(data_dir)
    check_capacity(accounts, account["id"])
    accounts[account["id"]] = account
    write_accounts(accounts, data_dir)
    return public_account(account)


def check_capacity(accounts: dict[str, dict], identity: str) -> None:
    if identity not in accounts and len(accounts) >= 10:
        raise MailboxLimit("Up to 10 additional mailboxes can be connected.")
