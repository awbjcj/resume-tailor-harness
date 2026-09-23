import json
from pathlib import Path

import pytest

from resume_tailor_harness.config import Settings
from resume_tailor_harness.gmail import auth
from resume_tailor_harness.gmail.errors import GmailApiError, GmailNotConnected
from resume_tailor_harness.tenancy.context import UserContext, use_context
from resume_tailor_harness.tenancy.workspace import workspace_paths


def _context(tmp_path: Path) -> UserContext:
    paths = workspace_paths(tmp_path, "u1")
    paths.root.mkdir(parents=True, exist_ok=True)
    return UserContext(
        user_id="u1",
        username="u1",
        role="member",
        paths=paths,
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        engine=None,
        system_engine=None,
        own_key_providers=frozenset(),
    )


def _token_payload(scopes: list[str]) -> str:
    return json.dumps(
        {
            "token": "ya29.fake",
            "refresh_token": "refresh",
            "client_id": "cid",
            "client_secret": "csecret",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": scopes,
            "expiry": "2099-01-01T00:00:00Z",
        }
    )


def test_token_path_prefers_context_then_data_dir(tmp_path: Path):
    with use_context(_context(tmp_path)):
        assert auth.token_path() == tmp_path / "users" / "u1" / "gmail_token.json"
    assert auth.token_path(tmp_path) == tmp_path / "gmail_token.json"
    assert auth.token_path() == Path("data/gmail_token.json")


def test_load_credentials_absent_returns_none(tmp_path: Path):
    assert auth.load_credentials(tmp_path) is None


def test_load_and_scope_check_round_trip(tmp_path: Path):
    auth.save_token_json(_token_payload(auth.GMAIL_SCOPES), tmp_path)
    creds = auth.load_credentials(tmp_path)
    assert creds is not None
    assert auth.has_compose(creds)

    auth.save_token_json(_token_payload([auth.SCOPE_READONLY]), tmp_path)
    creds = auth.load_credentials(tmp_path)
    assert creds is not None
    assert not auth.has_compose(creds)


def test_delete_token(tmp_path: Path):
    auth.save_token_json(_token_payload(auth.GMAIL_SCOPES), tmp_path)
    assert auth.delete_token(tmp_path) is True
    assert auth.delete_token(tmp_path) is False


def test_build_service_raises_when_disconnected(tmp_path: Path):
    with pytest.raises(GmailNotConnected):
        auth.build_service(tmp_path)


def _expired_token(tmp_path):
    raw = json.loads(_token_payload(auth.GMAIL_SCOPES))
    raw["expiry"] = "2000-01-01T00:00:00Z"
    return auth.save_token_json(json.dumps(raw), tmp_path)


def test_refresh_transport_failure_retries_and_persists(tmp_path, monkeypatch):
    from datetime import datetime
    from google.auth.exceptions import TransportError
    from google.oauth2.credentials import Credentials

    path = _expired_token(tmp_path)
    calls = []

    def refresh(creds, request):
        calls.append(request)
        assert request.keywords["timeout"] == 30
        if len(calls) == 1:
            raise TransportError("temporary network error")
        creds.token = "new-access-token"
        creds.expiry = datetime(2099, 1, 1)

    monkeypatch.setattr(Credentials, "refresh", refresh)
    monkeypatch.setattr(auth.time, "sleep", lambda _: None)
    credentials = auth.load_credentials(tmp_path)
    assert credentials is not None
    assert credentials.token == "new-access-token"
    assert len(calls) == 2
    assert json.loads(path.read_text())["token"] == "new-access-token"


@pytest.mark.parametrize("error_kind", ["transport", "retryable", "configuration"])
def test_temporary_refresh_failure_preserves_connection(
    tmp_path, monkeypatch, error_kind
):
    from google.auth.exceptions import RefreshError, TransportError
    from google.oauth2.credentials import Credentials

    path = _expired_token(tmp_path)
    before = path.read_bytes()
    errors = {
        "transport": TransportError("offline"),
        "retryable": RefreshError(
            "unavailable", {"error": "server_error"}, retryable=True
        ),
        "configuration": RefreshError("bad client", {"error": "invalid_client"}),
    }
    calls = []

    def refresh(*_):
        calls.append(1)
        raise errors[error_kind]

    monkeypatch.setattr(Credentials, "refresh", refresh)
    monkeypatch.setattr(auth.time, "sleep", lambda _: None)
    with pytest.raises(GmailApiError):
        auth.load_credentials(tmp_path)
    assert path.read_bytes() == before
    assert len(calls) == (3 if error_kind == "transport" else 1)


def test_revoked_token_is_retired_until_reconnected(tmp_path, monkeypatch):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    path = _expired_token(tmp_path)

    def refresh(*_):
        raise RefreshError("revoked", {"error": "invalid_grant"})

    monkeypatch.setattr(Credentials, "refresh", refresh)
    assert auth.load_credentials(tmp_path) is None
    assert not path.exists()
    assert auth.load_credentials(tmp_path) is None


def test_concurrent_loads_refresh_once(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime
    from threading import Barrier
    from google.oauth2.credentials import Credentials

    path = _expired_token(tmp_path)
    barrier = Barrier(2)
    calls = []

    def refresh(creds, _):
        calls.append(1)
        creds.token = "refreshed"
        creds.expiry = datetime(2099, 1, 1)

    def load():
        barrier.wait(timeout=5)
        credentials = auth.load_credentials(tmp_path)
        assert credentials is not None
        return credentials.token

    monkeypatch.setattr(Credentials, "refresh", refresh)
    with ThreadPoolExecutor(max_workers=2) as executor:
        a, b = executor.submit(load), executor.submit(load)
        assert a.result(timeout=5) == b.result(timeout=5) == "refreshed"
    assert calls == [1]
    assert json.loads(path.read_text())["token"] == "refreshed"


def test_missing_access_token_refreshes_even_before_expiry(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials

    raw = json.loads(_token_payload(auth.GMAIL_SCOPES))
    raw["token"] = None
    auth.save_token_json(json.dumps(raw), tmp_path)

    def refresh(creds, _):
        creds.token = "recovered"

    monkeypatch.setattr(Credentials, "refresh", refresh)
    credentials = auth.load_credentials(tmp_path)
    assert credentials is not None
    assert credentials.token == "recovered"
