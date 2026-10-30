from io import BytesIO
from unittest.mock import Mock
import imaplib
import re

import httpx
import pytest

from resume_tailor_harness.api.runs.manager import RunCancelled
from resume_tailor_harness.config import Settings
from resume_tailor_harness.mailboxes import imap, microsoft
from resume_tailor_harness.mailboxes.models import MailboxError
from resume_tailor_harness.security.mail_transport import (
    IMAP_LITERAL_LIMIT,
    PublicIMAPSSL,
)
from resume_tailor_harness.services.mailboxes import _analyze
from tests.test_gmail_incremental_sync import _seed
from tests.test_mailboxes import FakeIMAP


@pytest.mark.parametrize("attributes_after_body", [False, True])
@pytest.mark.parametrize("lowercase", [False, True])
def test_imap_uses_complete_fetch_records_from_real_parser(
    attributes_after_body, lowercase, monkeypatch
):
    client = object.__new__(PublicIMAPSSL)
    client._mode_ascii()
    client.debug = 4
    monkeypatch.setattr(client, "_mesg", Mock(), raising=False)
    monkeypatch.setattr(
        client,
        "tagre",
        re.compile(rb"(?P<tag>Z[0-9]+) (?P<type>[A-Z]+) (?P<data>.*)"),
        raising=False,
    )
    client.tagged_commands = {}
    client.untagged_responses = {}
    # Different arrival order, UID after the body, and flag updates are valid.
    wire = []
    for uid in [2, 1]:
        raw = f"From: hr@example.com\r\nSubject: Update\r\n\r\nMessage {uid}".encode()
        attributes = f'FLAGS (UID 999 "UID 888") UID {uid} INTERNALDATE "29-Oct-2026 12:00:00 -0400"'.encode()
        if lowercase:
            attributes = attributes.replace(b"UID", b"uid").replace(
                b"INTERNALDATE", b"internaldate"
            )
        before, after = (
            (b"", b" " + attributes)
            if attributes_after_body
            else (attributes + b" ", b"")
        )
        wire.append(
            b"* "
            + str(uid).encode()
            + b" FETCH ("
            + before
            + b"BODY[]<0> {"
            + str(len(raw)).encode()
            + b"}\r\n"
            + raw
            + after
            + b")\r\n"
        )
        wire.append(b"* 3 FETCH (UID 3 FLAGS (\\Seen))\r\n")
    client.file = BytesIO(b"".join(wire))
    with client.bounded_response(lambda: None):
        for _ in wire:
            client._get_response()
    payload = client.untagged_responses["FETCH"]

    class ParsedIMAP(FakeIMAP):
        def uid(self, command, *args):
            return (
                ("OK", payload) if command == "fetch" else super().uid(command, *args)
            )

    emails, cursor, more = imap.read_page(
        ParsedIMAP([1, 2]), {}, 2, lambda: None, bounds=(7, 2)
    )
    assert [(email.message_id, email.body) for email in emails] == [
        ("7:2", "Message 2"),
        ("7:1", "Message 1"),
    ]
    assert all(email.internal_date == 1793289600000 for email in emails)
    assert cursor["before"] == 0 and not more


@pytest.mark.parametrize("failure", [None, "cancel", "provider"])
def test_graph_read_pass_reuses_and_always_closes_client(monkeypatch, failure):
    clients = []
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer fixture-token"
        if failure == "provider" and len(requests) == 2:
            return httpx.Response(500, json={"error": {"code": "unavailable"}})
        cursor = "@odata.deltaLink" if len(requests) == 5 else "@odata.nextLink"
        return httpx.Response(
            200, json={"value": [], cursor: microsoft.DELTA + f"?page={len(requests)}"}
        )

    original = httpx.Client

    def create(**kwargs):
        assert kwargs == {"timeout": 30, "trust_env": False, "follow_redirects": False}
        client = original(**kwargs, transport=httpx.MockTransport(respond))
        clients.append(client)
        return client

    monkeypatch.setattr(microsoft.httpx, "Client", create)
    reporter = Mock()
    if failure == "cancel":
        reporter.checkpoint.side_effect = [None, RunCancelled()]
    engine = _seed()
    try:
        account = {
            "id": "fixture",
            "provider": "microsoft",
            "token": {"access_token": "fixture-token"},
        }
        settings = Settings(gmail_max_ai_calls=0, gmail_sync_max_pages=5)
        if failure:
            with pytest.raises(RunCancelled if failure == "cancel" else MailboxError):
                _analyze(engine, reporter, account, settings, [])
        else:
            assert not _analyze(engine, reporter, account, settings, [])["has_more"]
        assert len(clients) == 1 and clients[0].is_closed
        assert len(requests) == ({None: 5, "cancel": 1, "provider": 2}[failure])
    finally:
        engine.dispose()


def test_imap_batches_preserve_selected_order_and_reduce_commands():
    client = FakeIMAP(list(range(1, 101)))
    emails, cursor, more = imap.read_page(
        client, {}, 100, lambda: None, bounds=(7, 100)
    )
    assert [email.message_id for email in emails] == [
        f"7:{i}" for i in range(100, 0, -1)
    ]
    assert len(client.fetches) == 13
    assert all(len(uids) <= 8 for uids, _ in client.fetches)
    assert cursor["before"] == 0 and not more


@pytest.mark.parametrize(
    "failure", ["duplicate", "unsolicited", "missing_uid", "oversized", "late"]
)
def test_invalid_imap_batches_leave_cursor_unchanged(failure):
    class InvalidBatch(FakeIMAP):
        def uid(self, command, *args):
            result = super().uid(command, *args)
            if command != "fetch":
                return result
            status, payload = result
            if failure == "late":
                return ("NO", []) if len(self.fetches) == 2 else result
            if failure == "duplicate":
                payload.append(payload[0])
            elif failure == "unsolicited":
                payload.append(
                    (b'1 (UID 999 INTERNALDATE "29-Oct-2026 12:00:00 -0400")', b"")
                )
            elif failure == "missing_uid":
                payload[0] = (b'1 (INTERNALDATE "29-Oct-2026 12:00:00 -0400")', b"")
            elif failure == "oversized":
                payload[0] = (payload[0][0], b"x" * (IMAP_LITERAL_LIMIT + 1))
            return status, payload

    cursor = {"validity": 7, "high": 20, "before": 20}
    with pytest.raises(MailboxError):
        imap.read_page(
            InvalidBatch(list(range(1, 21))), cursor, 20, lambda: None, bounds=(7, 20)
        )
    assert cursor == {"validity": 7, "high": 20, "before": 20}


def test_expunged_uid_is_skipped_without_associating_other_messages_to_it():
    class Expunged(FakeIMAP):
        def uid(self, command, *args):
            status, payload = super().uid(command, *args)
            return status, payload[1:] if command == "fetch" else payload

    emails, cursor, _ = imap.read_page(
        Expunged([1, 2, 3]), {}, 3, lambda: None, bounds=(7, 3)
    )
    assert [email.message_id for email in emails] == ["7:3", "7:2"]
    assert cursor["before"] == 0


def test_imap_aggregate_budget_rejects_extra_literals_before_reading():
    client = object.__new__(PublicIMAPSSL)
    client.file = BytesIO(b"x" * (IMAP_LITERAL_LIMIT * 9))
    with client.bounded_response(lambda: None):
        for _ in range(8):
            assert len(client.read(IMAP_LITERAL_LIMIT)) == IMAP_LITERAL_LIMIT
        with pytest.raises(imaplib.IMAP4.abort):
            client.read(1)
    assert client.file.tell() == IMAP_LITERAL_LIMIT * 8


def test_imap_metadata_budget_caps_the_read_allocation():
    client = object.__new__(PublicIMAPSSL)
    client.file = BytesIO(b"x" * (1024 * 1024))
    with client.bounded_response(lambda: None), pytest.raises(imaplib.IMAP4.abort):
        client.readline()
    assert client.file.tell() == 64 * 1024 + 1


def test_imap_cancellation_is_checked_inside_response_consumption():
    client = object.__new__(PublicIMAPSSL)
    client.file = BytesIO(b"abc")
    checkpoint = Mock(side_effect=RunCancelled())
    with client.bounded_response(checkpoint), pytest.raises(RunCancelled):
        client.read(3)
    assert client.file.tell() == 0
