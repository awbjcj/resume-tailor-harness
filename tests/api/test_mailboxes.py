from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.mailboxes import imap, microsoft
from resume_tailor_harness.mailboxes.models import MailboxError

PAYLOAD = {
    "provider": "custom",
    "email": "me@example.com",
    "imap": {
        "host": "imap.example.com",
        "port": 993,
        "security": "tls",
        "username": "me@example.com",
        "password": "private-password",
    },
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(imap, "verify_connection", lambda body: None)
    app = create_app(
        db_url="sqlite://",
        config_dir=tmp_path / "config",
        env_path=tmp_path / ".env",
        data_dir=tmp_path / "data",
    )
    with TestClient(app) as client:
        yield client


def enable_microsoft(app):
    app.state.settings = app.state.settings.model_copy(
        update={
            "microsoft_oauth_client_id": "client-id",
            "microsoft_oauth_client_secret": "client-secret",
        }
    )


def test_create_list_disconnect_redacts_secrets(client):
    result = client.post("/api/mailboxes", json=PAYLOAD)
    assert result.status_code == 201 and result.headers["cache-control"] == "no-store"
    assert "private-password" not in result.text and "imap" not in result.json()
    accounts = client.get("/api/mailboxes").json()
    assert len(accounts["accounts"]) == 1 and len(accounts["providers"]) == 5
    assert "private-password" not in str(accounts)
    account_id = result.json()["id"]
    assert client.delete("/api/mailboxes/" + account_id).status_code == 204
    assert client.get("/api/mailboxes").json()["accounts"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"port": 0},
        {"security": "none"},
        {"host": "https://imap.example.com"},
        {"host": "x\r\npassword=private-password"},
        {"password": ""},
    ],
)
def test_invalid_input_does_not_echo_password(client, changes):
    response = client.post(
        "/api/mailboxes", json={**PAYLOAD, "imap": {**PAYLOAD["imap"], **changes}}
    )
    assert response.status_code == 422
    assert "private-password" not in response.text
    details = response.json()["error"]["details"]
    assert details[0]["loc"] == ["body", "imap", next(iter(changes))]
    assert set(details[0]) == {"loc", "type"}


def test_failed_verification_never_persists(client, monkeypatch):
    monkeypatch.setattr(
        imap, "verify_connection", Mock(side_effect=MailboxError("Access failed."))
    )
    assert client.post("/api/mailboxes", json=PAYLOAD).status_code == 503
    assert client.get("/api/mailboxes").json()["accounts"] == []


def test_authentication_failure_has_safe_field_locations(client, monkeypatch):
    from resume_tailor_harness.mailboxes.models import MailboxCredentials

    monkeypatch.setattr(
        imap,
        "verify_connection",
        Mock(
            side_effect=MailboxCredentials(
                "IMAP sign-in failed.",
                fields=("imap.username", "imap.password"),
            )
        ),
    )
    response = client.post("/api/mailboxes", json=PAYLOAD)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MAILBOX_CREDENTIALS"
    assert response.json()["error"]["details"][1]["loc"] == ["body", "imap", "password"]
    assert "private-password" not in response.text
    assert client.get("/api/mailboxes").json()["accounts"] == []


def test_conflicting_mailbox_operation_is_not_an_outage(client):
    from resume_tailor_harness.mailboxes.store import connection_lock

    with connection_lock(client.app.state.data_dir):
        response = client.post("/api/mailboxes", json=PAYLOAD)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MAILBOX_BUSY"


def test_sync_uses_background_run_and_rejects_unknown_account(client, monkeypatch):
    from resume_tailor_harness.services import mailboxes

    monkeypatch.setattr(mailboxes, "run_mailbox_sync", lambda *a, **k: {"pending": 0})
    assert client.post("/api/mailboxes/missing/sync").status_code == 404
    account = client.post("/api/mailboxes", json=PAYLOAD).json()
    result = client.post(f"/api/mailboxes/{account['id']}/sync")
    assert result.status_code == 202 and result.json()["kind"] == "mailboxSync"


def test_microsoft_missing_configuration_is_visible(client):
    assert not client.get("/api/mailboxes").json()["providers"][0]["available"]
    assert client.get("/api/mailboxes/microsoft/connect").status_code == 503


def fake_connect(*args):
    return {
        "id": "microsoft-account",
        "provider": "microsoft",
        "email": "me@outlook.com",
        "token": {
            "access_token": "private-token",
            "refresh_token": "refresh",
            "expires_at": 9999999999,
        },
    }


def test_oauth_pkce_browser_binding_and_single_use(client, monkeypatch):
    enable_microsoft(client.app)
    exchange = Mock(side_effect=fake_connect)
    monkeypatch.setattr(microsoft, "connect", exchange)
    start = client.get("/api/mailboxes/microsoft/connect")
    query = parse_qs(urlsplit(start.json()["authUrl"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "Mail.Read" in query["scope"][0] and "Mail.Send" not in query["scope"][0]
    assert "HttpOnly" in start.headers["set-cookie"]
    assert "Path=/api/mailboxes/microsoft/callback" in start.headers["set-cookie"]
    assert "SameSite=lax" in start.headers["set-cookie"]
    params = {"state": query["state"][0], "code": "valid"}
    response = client.get(
        "/api/mailboxes/microsoft/callback", params=params, follow_redirects=False
    )
    assert response.headers["location"].endswith("mailbox=connected")
    assert exchange.call_args.args[-1] != query["code_challenge"][0]
    assert exchange.call_args.args[-1] not in start.headers["set-cookie"]
    assert query["state"][0] not in start.headers["set-cookie"]
    response = client.get(
        "/api/mailboxes/microsoft/callback", params=params, follow_redirects=False
    )
    assert response.headers["location"].endswith("mailbox=invalid")
    assert exchange.call_count == 1
    assert "private-token" not in client.get("/api/mailboxes").text


def test_oauth_rejects_callback_without_browser_cookie(client, monkeypatch):
    enable_microsoft(client.app)
    exchange = Mock(side_effect=fake_connect)
    monkeypatch.setattr(microsoft, "connect", exchange)
    start = client.get("/api/mailboxes/microsoft/connect")
    state = parse_qs(urlsplit(start.json()["authUrl"]).query)["state"][0]
    client.cookies.clear()
    result = client.get(
        "/api/mailboxes/microsoft/callback",
        params={"state": state, "code": "valid"},
        follow_redirects=False,
    )
    assert result.headers["location"].endswith("mailbox=invalid")
    exchange.assert_not_called()


def test_local_persistent_workspace_oauth_without_session_secret(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "MICROSOFT_OAUTH_CLIENT_ID=id\nMICROSOFT_OAUTH_CLIENT_SECRET=secret\n"
    )
    app = create_app(
        db_url=f"sqlite:///{(tmp_path / 'local.db').as_posix()}",
        env_path=env,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
    )
    monkeypatch.setattr(microsoft, "connect", fake_connect)
    with TestClient(app) as client:
        assert not app.state.settings.session_secret
        start = client.get("/api/mailboxes/microsoft/connect")
        state = parse_qs(urlsplit(start.json()["authUrl"]).query)["state"][0]
        result = client.get(
            "/api/mailboxes/microsoft/callback",
            params={"state": state, "code": "valid"},
            follow_redirects=False,
        )
        assert result.headers["location"].endswith("mailbox=connected")
        assert len(client.get("/api/mailboxes").json()["accounts"]) == 1


def test_hosted_routes_require_authentication(mu_client):
    assert mu_client.get("/api/mailboxes").status_code == 401
    assert mu_client.post("/api/mailboxes", json=PAYLOAD).status_code == 401


def test_hosted_oauth_writes_only_signed_owners_workspace(mu_app, monkeypatch):
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from resume_tailor_harness.tenancy.system_db import User
    from resume_tailor_harness.tenancy.workspace import workspace_paths
    from resume_tailor_harness.mailboxes.store import FILENAME

    monkeypatch.setattr(microsoft, "connect", fake_connect)
    with TestClient(mu_app, base_url="https://testserver") as client:
        enable_microsoft(mu_app)
        assert (
            client.post(
                "/api/auth/login",
                json={"identifier": "owner", "password": "owner-password"},
            ).status_code
            == 200
        )
        start = client.get("/api/mailboxes/microsoft/connect")
        assert "Secure" in start.headers["set-cookie"]
        state = parse_qs(urlsplit(start.json()["authUrl"]).query)["state"][0]
        result = client.get(
            "/api/mailboxes/microsoft/callback",
            params={"state": state, "code": "valid"},
            follow_redirects=False,
        )
        assert result.headers["location"].endswith("mailbox=connected")
        with Session(mu_app.state.system_engine) as session:
            user = session.execute(
                select(User).where(User.username == "owner")
            ).scalar_one()
            assert (
                workspace_paths(mu_app.state.data_dir, user.id).root / FILENAME
            ).is_file()
        assert not (mu_app.state.data_dir / FILENAME).exists()
