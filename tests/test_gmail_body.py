import base64

from resume_tailor_harness.gmail.classify import hydrating_classifier
from resume_tailor_harness.gmail.client import (
    EmailMessage,
    extract_body,
    fetch_message_body,
)


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _payload_plain(text: str) -> dict:
    return {"mimeType": "text/plain", "body": {"data": _b64(text)}}


def test_extract_body_prefers_text_plain_in_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>HTML version</p>")}},
            _payload_plain("plain version"),
        ],
    }
    assert extract_body(payload) == "plain version"


def test_extract_body_falls_back_to_html():
    payload = {
        "mimeType": "text/html",
        "body": {"data": _b64("<p>Hello <b>there</b></p>")},
    }
    assert "Hello" in extract_body(payload)
    assert "<p>" not in extract_body(payload)


def test_extract_body_truncates():
    payload = _payload_plain("x" * 10_000)
    assert len(extract_body(payload)) <= 4000


class _FakeMessages:
    def __init__(self, payload):
        self._payload = payload

    def get(self, userId, id, format):
        payload = self._payload
        return type(
            "Req", (), {"execute": staticmethod(lambda **_: {"payload": payload})}
        )()


class _FakeService:
    def __init__(self, payload):
        self._messages = _FakeMessages(payload)

    def users(self):
        messages = self._messages
        return type("Users", (), {"messages": staticmethod(lambda: messages)})()


def test_fetch_message_body_via_service():
    service = _FakeService(_payload_plain("Unfortunately we will not proceed."))
    assert "Unfortunately" in fetch_message_body(service, "m1")


def test_hydrating_classifier_uses_body_rules():
    service = _FakeService(_payload_plain("Unfortunately we chose other candidates."))
    classify = hydrating_classifier(service, llm=None)
    email = EmailMessage(
        sender="hr@acme.com",
        sender_domain="acme.com",
        subject="Your application",
        snippet="Update on your application",
        message_id="m1",
    )
    assert classify(email) == "rejection"
    assert email.body is not None  # hydrated in place, fetched once


def test_body_outage_uses_snippet_and_reports_warning(monkeypatch):
    from unittest.mock import Mock
    from resume_tailor_harness.gmail import client
    from resume_tailor_harness.gmail.errors import GmailApiError

    monkeypatch.setattr(
        client, "fetch_message_body", Mock(side_effect=GmailApiError("offline"))
    )
    warnings = []
    classify = hydrating_classifier(None, None, on_warning=warnings.append)
    email = EmailMessage(
        "hr@acme.com", "acme.com", "Update", "Interview invitation", message_id="m1"
    )
    assert classify(email) == "interview"
    assert warnings == ["Some email bodies could not be read. Used available snippets."]


def test_body_auth_error_is_not_silently_ignored(monkeypatch):
    from unittest.mock import Mock
    import pytest
    from resume_tailor_harness.gmail import client
    from resume_tailor_harness.gmail.errors import GmailNotConnected

    monkeypatch.setattr(
        client, "fetch_message_body", Mock(side_effect=GmailNotConnected("reconnect"))
    )
    classify = hydrating_classifier(None, None)
    with pytest.raises(GmailNotConnected):
        classify(
            EmailMessage(
                "hr@acme.com", "acme.com", "Update", "Interview", message_id="m1"
            )
        )
