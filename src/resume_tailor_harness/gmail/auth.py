"""Tenant-aware Gmail credential storage + service construction.

Tokens are per-user workspace files (never DB rows). The interactive
InstalledAppFlow survives for the local CLI only; the web flow lives in
api/routers/gmail.py. Google SDK imports stay lazy so the offline test
suite never needs them on the import path.
"""

from __future__ import annotations

import time
from functools import partial
from pathlib import Path
from threading import RLock
from typing import Any

from resume_tailor_harness.gmail.errors import GmailApiError, GmailNotConnected
from resume_tailor_harness.progress import atomic_write_text
from resume_tailor_harness.tenancy.context import current_context

SCOPE_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_SCOPES = [SCOPE_READONLY, SCOPE_COMPOSE]
CREDENTIALS_PATH = "config/gmail_credentials.json"
_LEGACY_TOKEN_PATH = Path("data/gmail_token.json")
HTTP_TIMEOUT_SECONDS = 30
# Bounded lock storage; refresh, connect, and disconnect share the same lock.
_TOKEN_LOCKS = tuple(RLock() for _ in range(32))


def _token_lock(path: Path):
    return _TOKEN_LOCKS[hash(path.resolve()) % len(_TOKEN_LOCKS)]


def token_path(data_dir: Path | None = None) -> Path:
    """Active workspace token, else <data_dir>/gmail_token.json, else legacy."""
    context = current_context()
    if context is not None:
        return context.paths.gmail_token
    if data_dir is not None:
        return Path(data_dir) / "gmail_token.json"
    return _LEGACY_TOKEN_PATH


def save_token_json(raw: str, data_dir: Path | None = None) -> Path:
    path = token_path(data_dir)
    with _token_lock(path):
        atomic_write_text(path, raw, root=path.parent)
    return path


def delete_token(data_dir: Path | None = None) -> bool:
    path = token_path(data_dir)
    with _token_lock(path):
        if not path.is_file():
            return False
        path.unlink()
        return True


def load_credentials(data_dir: Path | None = None) -> Any | None:
    """Refresh once per workspace; temporary failures never mean disconnected."""
    path = token_path(data_dir)
    with _token_lock(path):
        return _load_credentials(path)


def _load_credentials(path: Path) -> Any | None:
    if not path.is_file():
        return None
    from google.auth.exceptions import RefreshError, TransportError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        creds = Credentials.from_authorized_user_file(str(path))
    except ValueError:
        return None
    if creds.valid:
        return creds
    if creds.refresh_token:
        import requests

        with requests.Session() as session:
            request = partial(Request(session=session), timeout=HTTP_TIMEOUT_SECONDS)
            for attempt in range(3):
                try:
                    creds.refresh(request)
                    break
                except RefreshError as exc:
                    # Google-auth already retries temporary token endpoint errors.
                    # Only an explicit invalid_grant proves this token is unusable.
                    revoked = any(
                        isinstance(arg, dict) and arg.get("error") == "invalid_grant"
                        for arg in exc.args
                    )
                    if revoked and not exc.retryable:
                        path.unlink(missing_ok=True)
                        return None
                    raise GmailApiError(
                        "Gmail could not refresh its connection. Try syncing again later."
                    ) from exc
                except TransportError as exc:
                    if attempt == 2:
                        raise GmailApiError(
                            "Google is temporarily unreachable. Try syncing again later."
                        ) from exc
                    time.sleep(2**attempt)
        atomic_write_text(path, creds.to_json(), root=path.parent)
        return creds
    return None


def granted_scopes(creds: Any) -> list[str]:
    return list(creds.scopes or [])


def has_compose(creds: Any) -> bool:
    return SCOPE_COMPOSE in granted_scopes(creds)


def build_service(data_dir: Path | None = None) -> Any:
    """Authenticated Gmail service for the active tenant, or GmailNotConnected."""
    creds = load_credentials(data_dir)
    if creds is None:
        raise GmailNotConnected("Connect Gmail again in Settings to resume syncing.")
    return _build_service(creds)


def _build_service(creds: Any) -> Any:
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build

    return build(
        "gmail",
        "v1",
        http=AuthorizedHttp(creds, http=httplib2.Http(timeout=HTTP_TIMEOUT_SECONDS)),
        cache_discovery=False,
    )


def build_gmail_service_interactive(credentials_path: str = CREDENTIALS_PATH) -> Any:
    """CLI-only: reuse a stored token, else run the local-browser consent flow."""
    creds = load_credentials()
    if creds is None:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, GMAIL_SCOPES)
        creds = flow.run_local_server(port=0)
        save_token_json(creds.to_json())
    return _build_service(creds)
