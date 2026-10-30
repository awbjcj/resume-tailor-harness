from unittest.mock import Mock

import httpx
import pytest

from resume_tailor_harness.config import Settings
from resume_tailor_harness.mailboxes import microsoft, store
from resume_tailor_harness.mailboxes.models import MailboxError
from resume_tailor_harness.services.mailboxes import run_mailbox_sync
from tests.test_gmail_incremental_sync import _seed


@pytest.fixture
def mock_http(monkeypatch):
    real_client = httpx.Client

    def install(handler):
        monkeypatch.setattr(
            microsoft.httpx,
            "Client",
            lambda **kwargs: real_client(
                transport=httpx.MockTransport(handler), **kwargs
            ),
        )

    return install


def settings():
    return Settings(
        microsoft_oauth_client_id="client",
        microsoft_oauth_client_secret="client-secret",
        gmail_max_ai_calls=0,
    )


def expired_account():
    return {
        "id": "ms",
        "provider": "microsoft",
        "email": "me@example.com",
        "token": {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": 0,
        },
    }


def test_refresh_rotates_token_and_keeps_existing_refresh_when_omitted(mock_http):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "scope": "User.Read Mail.Read",
                "expires_in": 3600,
            },
        )

    mock_http(respond)
    account = expired_account()
    microsoft.refresh(account, settings())
    assert account["token"]["access_token"] == "new-access"
    assert account["token"]["refresh_token"] == "old-refresh"
    assert b"grant_type=refresh_token" in requests[0].content
    assert b"client_secret=client-secret" in requests[0].content
    assert str(requests[0].url) == microsoft.AUTHORITY + "/token"


@pytest.mark.parametrize(
    "status,error,reconnect",
    [
        (400, "invalid_grant", True),
        (503, "temporarily_unavailable", False),
    ],
)
def test_refresh_failure_preserves_credentials_and_marks_only_revocation(
    tmp_path, mock_http, status, error, reconnect
):
    mock_http(
        lambda request: httpx.Response(
            status,
            json={"error": error, "error_description": "private-token-provider-detail"},
        )
    )
    store.write_accounts({"ms": expired_account()}, tmp_path)
    with pytest.raises(MailboxError) as failure:
        run_mailbox_sync(
            _seed(), Mock(), account_id="ms", data_dir=tmp_path, settings=settings()
        )
    assert "private-token-provider-detail" not in str(failure.value)
    account = store.read_accounts(tmp_path)["ms"]
    assert account["token"]["refresh_token"] == "old-refresh"
    assert bool(account.get("needs_reconnect")) == reconnect


def test_missing_read_scope_never_connects(mock_http):
    mock_http(
        lambda request: httpx.Response(
            200,
            json={
                "access_token": "token",
                "refresh_token": "refresh",
                "scope": "User.Read",
            },
        )
    )
    with pytest.raises(microsoft.MicrosoftReconnect):
        microsoft.connect(
            settings(), "https://app.example/callback", "code", "verifier"
        )


def test_graph_redirect_is_not_followed_and_token_never_leaves_origin(mock_http):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/"})

    mock_http(respond)
    with pytest.raises(MailboxError):
        microsoft.graph_get(microsoft.DELTA, "private-token")
    assert len(requests) == 1 and requests[0].url.host == "graph.microsoft.com"


def test_expired_delta_restarts_with_same_receipt_identity(monkeypatch):
    getter = Mock(
        side_effect=[
            microsoft.DeltaExpired(),
            {"value": [], "@odata.deltaLink": microsoft.DELTA + "?$deltatoken=new"},
        ]
    )
    monkeypatch.setattr(microsoft, "graph_get", getter)
    _, cursor, more = microsoft.read_page(
        {"token": {"access_token": "token"}},
        {"delta": microsoft.DELTA + "?$deltatoken=old"},
    )
    assert not more and cursor["delta"].endswith("=new")
    assert len(getter.call_args_list) == 2


@pytest.mark.parametrize(
    "path",
    [
        "/v1.0/me/mailFolders/AAMkAGVm123=/messages/delta",
        "/v1.0/me/mailFolders('AAMkAGVm123=')/messages/delta",
    ],
)
def test_canonical_folder_continuations_are_supported(mock_http, path):
    mock_http(lambda request: httpx.Response(200, json={"value": []}))
    assert microsoft.graph_get(
        "https://graph.microsoft.com" + path + "?$skiptoken=x", "token"
    ) == {"value": []}


def test_outlook_404_sync_state_expiration_is_retryable(mock_http):
    mock_http(
        lambda request: httpx.Response(
            404, json={"error": {"code": "syncStateNotFound"}}
        )
    )
    with pytest.raises(microsoft.DeltaExpired):
        microsoft.graph_get(microsoft.DELTA + "?$deltatoken=expired", "token")


def test_null_graph_fields_are_normalized(monkeypatch):
    monkeypatch.setattr(
        microsoft,
        "graph_get",
        lambda *a: {
            "value": [
                {
                    "id": "a",
                    "from": None,
                    "subject": None,
                    "body": None,
                    "bodyPreview": None,
                    "receivedDateTime": "2026-10-29T12:00:00Z",
                }
            ],
            "@odata.deltaLink": microsoft.DELTA + "?$deltatoken=new",
        },
    )
    messages, _, _ = microsoft.read_page({"token": {"access_token": "token"}}, {})
    assert (
        messages[0].body == ""
        and messages[0].sender == ""
        and messages[0].subject == ""
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": ["private-provider-detail"]},
        {"access_token": {"private-token": True}},
        {"expires_in": None},
        {"expires_in": "NaN"},
        {"refresh_token": 42},
    ],
)
def test_malformed_tokens_are_safe_and_do_not_replace_credentials(mock_http, changes):
    mock_http(
        lambda request: httpx.Response(
            200,
            json={
                "access_token": "token",
                "scope": "Mail.Read User.Read",
                **changes,
            },
        )
    )
    account = expired_account()
    with pytest.raises(MailboxError) as failure:
        microsoft.refresh(account, settings())
    assert failure.value.status_code == 502
    assert "private" not in str(failure.value)
    assert account == expired_account()


@pytest.mark.parametrize(
    "changes",
    [
        {"value": None},
        {"value": ["private-message"]},
        {"value": [{"id": "a", "from": "private-address"}]},
        {"value": [{"id": 42}]},
        {"value": [{"id": "a", "body": {"content": {"private-body": 1}}}]},
        {"value": [{"id": "a", "receivedDateTime": "2026-10-29T12:00:00"}]},
        {"@odata.deltaLink": {"private-cursor": True}},
    ],
)
def test_malformed_graph_pages_fail_safely_before_advancing(monkeypatch, changes):
    monkeypatch.setattr(
        microsoft,
        "graph_get",
        lambda *a: {
            "value": [],
            "@odata.deltaLink": microsoft.DELTA + "?$deltatoken=new",
            **changes,
        },
    )
    cursor = {"delta": microsoft.DELTA + "?$deltatoken=old"}
    with pytest.raises(MailboxError) as failure:
        microsoft.read_page({"token": {"access_token": "token"}}, cursor)
    assert failure.value.status_code == 502 and "private" not in str(failure.value)
    assert cursor["delta"].endswith("=old")


def test_invalid_continuation_is_rejected_before_commit(monkeypatch):
    monkeypatch.setattr(
        microsoft,
        "graph_get",
        lambda *a: {
            "value": [],
            "@odata.nextLink": "https://evil.example/private-token",
        },
    )
    with pytest.raises(MailboxError):
        microsoft.read_page({"token": {"access_token": "token"}}, {})


def test_malformed_graph_error_does_not_escape_safe_envelope(mock_http):
    mock_http(lambda request: httpx.Response(503, json={"error": "private-detail"}))
    with pytest.raises(MailboxError) as failure:
        microsoft.graph_get(microsoft.DELTA, "token")
    assert "private" not in str(failure.value)
