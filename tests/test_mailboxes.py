from contextlib import contextmanager, nullcontext
from email.message import EmailMessage as MimeMessage
from unittest.mock import Mock
from typing import Any

import pytest
from sqlmodel import Session, select

from resume_tailor_harness.config import Settings
from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.gmail.tables import GmailReceipt, GmailSyncState
from resume_tailor_harness.mailboxes import imap, microsoft, store
from resume_tailor_harness.mailboxes.models import MailboxConnectIn, MailboxError
from resume_tailor_harness.security import mail_transport
from resume_tailor_harness.services import mailboxes
from resume_tailor_harness.tracking.tables import Application, Notification
from tests.test_gmail_incremental_sync import _seed


def config(**overrides):
    return MailboxConnectIn.model_validate(
        {
            "email": "me@example.com",
            "imap": {
                "host": "imap.example.com",
                "port": 993,
                "username": "me@example.com",
                "password": "private-password",
            },
            **overrides,
        }
    )


def message(mid="1", date=1000, decision="rejection"):
    text = "For R900000 Senior Engineer: " + (
        "We have decided not to move forward with your application."
        if decision == "rejection"
        else "Please schedule an interview with us."
    )
    return EmailMessage(
        sender="hr@employer0.com",
        sender_domain="employer0.com",
        subject="Application update",
        snippet=text,
        body=text,
        message_id=mid,
        internal_date=date,
        recruiting_candidate=True,
    )


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.1.1", "169.254.169.254", "::1"])
def test_private_targets_never_open_socket(monkeypatch, address):
    from resume_tailor_harness.security import outbound

    monkeypatch.setattr(
        outbound.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 0))]
    )
    connect = Mock()
    monkeypatch.setattr(mail_transport.socket, "create_connection", connect)
    with pytest.raises(ValueError):
        mail_transport.public_socket("mail.example.com", 993)
    connect.assert_not_called()


def test_cached_page_reads_current_catalog_and_receipts_in_two_queries():
    from sqlalchemy import event
    from resume_tailor_harness.gmail.classify import SyncClassifier
    from resume_tailor_harness.gmail.processing import MessageProcessor

    engine = _seed()
    emails = [message(str(i)) for i in range(100)]
    with Session(engine) as session:
        processor = MessageProcessor(
            None,
            session,
            "mailbox-ms",
            SyncClassifier(None, None, 0, lambda _: None),
            lambda: None,
            source="mailbox",
        )
        processor.process_emails(emails)
        session.commit()
        queries = []

        def count(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                queries.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            processor.process_emails(emails)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert processor.stats["cached"] == 100
        assert len(queries) == 2


def test_existing_workspace_gets_cross_account_index_without_losing_receipts():
    from resume_tailor_harness.db import init_db

    engine = _seed()
    with Session(engine) as session:
        session.add(
            GmailReceipt(account="old", message_id="preserved", application_id=1)
        )
        session.commit()
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX ix_gmail_receipt_global_application")
    init_db(engine)
    init_db(engine)
    with engine.connect() as connection:
        plan = connection.exec_driver_sql(
            "EXPLAIN QUERY PLAN SELECT account, message_id FROM gmail_receipts "
            "WHERE application_id IN (1) AND label != 'none' ORDER BY internal_date DESC"
        ).all()
        assert any(
            "USING INDEX ix_gmail_receipt_global_application" in row[3] for row in plan
        )
        assert (
            connection.exec_driver_sql("SELECT message_id FROM gmail_receipts").scalar()
            == "preserved"
        )


def test_duplicate_delta_ids_and_content_corrections_update_one_receipt():
    from resume_tailor_harness.gmail.classify import SyncClassifier
    from resume_tailor_harness.gmail.processing import MessageProcessor

    with Session(_seed()) as session:
        processor = MessageProcessor(
            None,
            session,
            "mailbox-ms",
            SyncClassifier(None, None, 0, lambda _: None),
            lambda: None,
            source="mailbox",
        )
        processor.process_emails([message(decision="interview"), message()])
        session.commit()
        assert session.exec(select(GmailReceipt)).one().label == "rejection"
        processor.process_emails([message(decision="interview")])
        session.commit()
        assert session.exec(select(GmailReceipt)).one().label == "interview"
        notices = session.exec(
            select(Notification).where(Notification.state == "pending")
        ).all()
        assert len(notices) == 1 and notices[0].proposed_status == "interview"


def test_new_mailbox_supersedes_legacy_gmail_notice_without_losing_its_identity():
    from resume_tailor_harness.gmail.classify import SyncClassifier
    from resume_tailor_harness.gmail.processing import MessageProcessor

    with Session(_seed()) as session:
        session.add(GmailSyncState(account="gmail-account"))
        session.commit()
        gmail = MessageProcessor(
            None,
            session,
            "gmail-account",
            SyncClassifier(None, None, 0, lambda _: None),
            lambda: None,
        )
        gmail.process_emails([message("old", date=1000, decision="interview")])
        old_notice = session.exec(select(Notification)).one()
        old_notice.message_id = "old"  # pre-account-namespacing Gmail notice
        session.add(old_notice)
        session.add(GmailSyncState(account="mailbox-ms"))
        session.commit()
        other = MessageProcessor(
            None,
            session,
            "mailbox-ms",
            SyncClassifier(None, None, 0, lambda _: None),
            lambda: None,
            source="mailbox",
        )
        other.process_emails([message("new", date=2000)])
        session.commit()
        pending = session.exec(
            select(Notification).where(Notification.state == "pending")
        ).all()
        assert len(pending) == 1 and pending[0].proposed_status == "rejected"
        session.refresh(old_notice)
        assert old_notice.state == "superseded"


def test_full_account_store_rejects_before_network_verification(tmp_path, monkeypatch):
    accounts = {
        str(i): {
            "id": str(i),
            "provider": "microsoft",
            "email": "me@example.com",
            "token": {"access_token": "token", "refresh_token": "refresh"},
        }
        for i in range(10)
    }
    store.write_accounts(accounts, tmp_path)
    verify = Mock()
    monkeypatch.setattr(imap, "verify_connection", verify)
    with pytest.raises(MailboxError) as failure:
        mailboxes.connect_custom(config(), tmp_path)
    assert failure.value.code == "MAILBOX_LIMIT"
    verify.assert_not_called()


def test_public_transport_pins_validated_address(monkeypatch):
    monkeypatch.setattr(
        mail_transport,
        "resolve_public_url",
        lambda url: ("mail.example.com", "8.8.8.8", 993),
    )
    connect = Mock()
    monkeypatch.setattr(mail_transport.socket, "create_connection", connect)
    mail_transport.public_socket("mail.example.com", 993)
    connect.assert_called_once_with(("8.8.8.8", 993), timeout=20)


def test_tls_verifies_original_hostname(monkeypatch):
    sock = Mock()
    monkeypatch.setattr(mail_transport, "public_socket", lambda *a: sock)
    client = object.__new__(mail_transport.PublicIMAPSSL)
    client.host, client.port = "mail.example.com", 993
    context = Mock()
    monkeypatch.setattr(client, "ssl_context", context, raising=False)
    client._create_socket(20)
    context.wrap_socket.assert_called_once_with(
        sock, server_hostname="mail.example.com"
    )


def test_starttls_precedes_login_and_selects_readonly(monkeypatch):
    client = Mock()
    client.select.return_value = ("OK", [b"2"])
    monkeypatch.setattr(imap, "PublicIMAP", lambda *a, **kw: client)
    body = config()
    body.imap.security = "starttls"
    body.imap.port = 143
    with imap.open_mailbox(body.imap, "INBOX"):
        pass
    names = [call[0] for call in client.mock_calls]
    assert names.index("starttls") < names.index("login") < names.index("select")
    client.select.assert_called_once_with('"INBOX"', readonly=True)
    client.logout.assert_called_once()


def test_tls_failure_does_not_send_password(monkeypatch):
    client = Mock()
    client.starttls.side_effect = OSError("unsafe private-password")
    monkeypatch.setattr(imap, "PublicIMAP", lambda *a, **kw: client)
    body = config()
    body.imap.security = "starttls"
    with pytest.raises(MailboxError) as error:
        with imap.open_mailbox(body.imap, "INBOX"):
            pass
    assert "private-password" not in str(error.value)
    client.login.assert_not_called()


def test_imap_auth_failure_is_distinct_from_transport_failure(monkeypatch):
    import imaplib

    client = Mock()
    monkeypatch.setattr(imap, "PublicIMAPSSL", lambda *a, **kw: client)
    for failure, code in [
        (imaplib.IMAP4.error("private-password"), "MAILBOX_CREDENTIALS"),
        (imaplib.IMAP4.abort("closed"), "MAILBOX_ERROR"),
    ]:
        client.login.side_effect = failure
        with pytest.raises(MailboxError) as caught:
            with imap.open_mailbox(config().imap, "INBOX"):
                pass
        assert caught.value.code == code
        assert "private-password" not in str(caught.value)


def test_smtp_is_verified_without_sending(monkeypatch):
    @contextmanager
    def mailbox(*args):
        yield Mock()

    monkeypatch.setattr(imap, "open_mailbox", mailbox)
    from unittest.mock import MagicMock

    wrapper = MagicMock()
    wrapper.__enter__.return_value = wrapper
    monkeypatch.setattr(imap, "PublicSMTPSSL", lambda *a, **kw: wrapper)
    body = config(smtp=config().imap.model_dump())
    imap.verify_connection(body)
    wrapper.login.assert_called_once_with("me@example.com", "private-password")
    wrapper.sendmail.assert_not_called()
    wrapper.send_message.assert_not_called()


def test_oversized_imap_literal_is_rejected_before_allocation():
    import imaplib

    client = object.__new__(mail_transport.PublicIMAPSSL)
    with pytest.raises(imaplib.IMAP4.abort):
        client.read(128 * 1024 + 1)


def test_mime_prefers_plain_and_excludes_attachment():
    msg = MimeMessage()
    msg["From"] = "Recruiter <hr@employer0.com>"
    msg["Subject"] = "申请更新"
    msg.set_content("Please schedule an interview.\nOn Monday someone wrote:\nRejected")
    msg.add_alternative("<p>HTML alternative</p>", subtype="html")
    msg.add_attachment(
        b"secret-attachment",
        maintype="application",
        subtype="octet-stream",
        filename="private.txt",
    )
    email = imap.parse_message(msg.as_bytes(), "7:9", 1234)
    assert email.subject == "申请更新"
    assert email.sender_domain == "employer0.com"
    assert email.body == "Please schedule an interview."
    assert "secret-attachment" not in str(email)


class FakeIMAP:
    def __init__(self, ids):
        self.ids = ids
        self.fetches = []
        self.fail = False

    def uid(self, command, *args) -> tuple[str, list[Any]]:
        if command == "search":
            low, high = map(int, args[-1].split(":"))
            return "OK", [
                " ".join(str(i) for i in self.ids if low <= i <= high).encode()
            ]
        uids = list(map(int, args[0].split(",")))
        self.fetches.append((uids, args[1]))
        if self.fail:
            return "NO", [b"private-password"]
        result = []
        for uid in reversed(uids):
            raw = (
                f"From: hr@employer0.com\r\nSubject: Update\r\n\r\nEmail {uid}".encode()
            )
            result.append(
                (
                    f'1 (UID {uid} INTERNALDATE "29-Oct-2026 12:00:00 -0400")'.encode(),
                    raw,
                )
            )
        return "OK", result

    def bounded_response(self, checkpoint):
        return nullcontext()


def test_imap_backfill_new_arrivals_and_uidvalidity():
    client = FakeIMAP([1, 2, 3, 4, 5])
    first, cursor, more = imap.read_page(client, {}, 2, lambda: None, bounds=(7, 5))
    assert [m.message_id for m in first] == ["7:5", "7:4"] and more
    client.ids += [6, 7]
    arrivals, cursor, more = imap.read_page(
        client, cursor, 2, lambda: None, bounds=(7, 7)
    )
    assert [m.message_id for m in arrivals] == ["7:6", "7:7"]
    old, cursor, more = imap.read_page(client, cursor, 2, lambda: None, bounds=(7, 7))
    assert [m.message_id for m in old] == ["7:3", "7:2"]
    last, cursor, more = imap.read_page(client, cursor, 2, lambda: None, bounds=(7, 7))
    assert [m.message_id for m in last] == ["7:1"] and not more
    idle, _, more = imap.read_page(client, cursor, 2, lambda: None, bounds=(7, 7))
    assert not idle and not more
    reset, _, _ = imap.read_page(client, cursor, 2, lambda: None, bounds=(8, 7))
    assert reset[0].message_id and reset[0].message_id.startswith("8:")
    assert all("BODY.PEEK[]<0.131072>" in parts for _, parts in client.fetches)


def test_imap_failure_leaves_cursor_retryable():
    client = FakeIMAP([1])
    client.fail = True
    cursor = {"validity": 7, "high": 1, "before": 1}
    with pytest.raises(MailboxError):
        imap.read_page(client, cursor, 2, lambda: None, bounds=(7, 1))
    assert cursor["before"] == 1


def test_verified_save_redacts_credentials_and_reconnects_in_place(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(imap, "verify_connection", lambda body: None)
    first = mailboxes.connect_custom(config(), tmp_path)
    again = mailboxes.connect_custom(config(), tmp_path)
    assert first.id == again.id
    assert "password" not in first.model_dump_json()
    assert len(store.read_accounts(tmp_path)) == 1
    assert (
        store.read_accounts(tmp_path)[first.id]["imap"]["password"]
        == "private-password"
    )
    monkeypatch.setattr(
        imap, "verify_connection", Mock(side_effect=MailboxError("bad connection"))
    )
    with pytest.raises(MailboxError):
        mailboxes.connect_custom(config(), tmp_path)
    assert len(store.read_accounts(tmp_path)) == 1
    mailboxes.disconnect(first.id, tmp_path)
    assert store.read_accounts(tmp_path) == {}


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/v1.0/me",
        "http://graph.microsoft.com/v1.0/me",
        "https://graph.microsoft.com@evil.example/v1.0/me",
        "https://graph.microsoft.com/v1.0/users",
        "https://graph.microsoft.com:443/v1.0/me",
    ],
)
def test_graph_continuations_cannot_leak_token(url, monkeypatch):
    network = Mock()
    monkeypatch.setattr(microsoft.httpx, "Client", network)
    with pytest.raises(MailboxError):
        microsoft.graph_get(url, "private-token")
    network.assert_not_called()


def test_microsoft_delta_normalization_and_continuation(monkeypatch):
    next_url = microsoft.DELTA + "?$skiptoken=x"
    page = {
        "value": [
            {"id": "gone", "@removed": {}},
            {"id": "draft", "isDraft": True},
            {
                "id": "incoming",
                "from": {"emailAddress": {"address": "hr@employer0.com"}},
                "subject": "Application update",
                "body": {
                    "contentType": "html",
                    "content": "<p>Interview</p><blockquote>Rejected</blockquote>",
                },
                "receivedDateTime": "2026-10-29T12:00:00Z",
            },
        ],
        "@odata.nextLink": next_url,
    }
    getter = Mock(return_value=page)
    monkeypatch.setattr(microsoft, "graph_get", getter)
    messages, cursor, more = microsoft.read_page(
        {"token": {"access_token": "secret"}}, {}
    )
    assert len(messages) == 1 and messages[0].body == "Interview"
    assert more and cursor["next"] == next_url
    getter.return_value = {
        "value": [],
        "@odata.deltaLink": microsoft.DELTA + "?$deltatoken=d",
    }
    _, cursor, more = microsoft.read_page({"token": {"access_token": "secret"}}, cursor)
    assert getter.call_args.args[0] == next_url and not more


def test_sync_analyzes_once_resumes_and_never_auto_applies(tmp_path, monkeypatch):
    engine = _seed()
    account = {
        "id": "ms",
        "provider": "microsoft",
        "email": "me@example.com",
        "token": {
            "access_token": "secret",
            "refresh_token": "refresh",
            "expires_at": 9999999999,
        },
    }
    store.write_accounts({"ms": account}, tmp_path)
    calls = []

    def read(account, cursor, **_transport):
        calls.append(cursor)
        return [message()], {"delta": "done"}, False

    monkeypatch.setattr(microsoft, "read_page", read)
    settings = Settings(gmail_max_ai_calls=0)
    result = mailboxes.run_mailbox_sync(
        engine, Mock(), account_id="ms", data_dir=tmp_path, settings=settings
    )
    assert result["pending"] == 1 and result["stats"]["processed"] == 1
    again = mailboxes.run_mailbox_sync(
        engine, Mock(), account_id="ms", data_dir=tmp_path, settings=settings
    )
    assert again["stats"]["cached"] == 1 and calls[-1] == {"delta": "done"}
    with Session(engine) as session:
        application = session.get(Application, 1)
        assert application and application.status == "submitted"
        assert len(session.exec(select(Notification)).all()) == 1
        assert (
            session.exec(select(GmailReceipt)).one().email_json["body"]
            == message().body
        )
    monkeypatch.setattr(
        microsoft, "read_page", Mock(side_effect=MailboxError("temporary"))
    )
    with pytest.raises(MailboxError):
        mailboxes.run_mailbox_sync(
            engine, Mock(), account_id="ms", data_dir=tmp_path, settings=settings
        )
    with Session(engine) as session:
        checkpoint = session.get(GmailSyncState, "mailbox-ms")
        assert checkpoint and checkpoint.cursors == {"delta": "done"}


def test_imap_service_reads_and_analyzes_incoming_mail(tmp_path, monkeypatch):
    engine = _seed()
    client = FakeIMAP([1])
    monkeypatch.setattr(
        client,
        "response",
        lambda key: ("OK", [b"7" if key == "UIDVALIDITY" else b"2"]),
        raising=False,
    )
    original_uid = client.uid

    def uid(command, *args):
        if command == "fetch":
            raw = (
                "From: hr@employer0.com\r\nSubject: Application update\r\n\r\n"
                "For R900000 Senior Engineer: We have decided not to move forward with your application."
            ).encode()
            return "OK", [(b'1 (UID 1 INTERNALDATE "29-Oct-2026 12:00:00 -0400")', raw)]
        return original_uid(command, *args)

    monkeypatch.setattr(client, "uid", uid)

    @contextmanager
    def connection(*args):
        yield client

    monkeypatch.setattr(imap, "open_mailbox", connection)
    connected = mailboxes.connect_custom(config(), tmp_path)
    result = mailboxes.run_mailbox_sync(
        engine,
        Mock(),
        account_id=connected.id,
        data_dir=tmp_path,
        settings=Settings(gmail_max_ai_calls=0),
    )
    assert result["pending"] == 1 and not result["has_more"]
    with Session(engine) as session:
        receipt = session.exec(select(GmailReceipt)).one()
        assert receipt.message_id == "7:1" and receipt.label == "rejection"


def test_scheduled_sync_isolates_failed_accounts(tmp_path, monkeypatch):
    accounts = {
        key: {
            "id": key,
            "provider": "microsoft",
            "email": key + "@example.com",
            "token": {"access_token": "token", "refresh_token": "refresh"},
        }
        for key in ["broken", "working", "revoked"]
    }
    accounts["revoked"]["needs_reconnect"] = True
    store.write_accounts(accounts, tmp_path)
    called = []

    def sync(*args, account_id, **kwargs):
        called.append(account_id)
        if account_id == "broken":
            raise MailboxError("Temporary outage.")
        return {"pending": 1}

    monkeypatch.setattr(mailboxes, "run_mailbox_sync", sync)
    result = mailboxes.run_connected_email_sync(_seed(), Mock(), data_dir=tmp_path)
    assert called == ["broken", "working"]
    assert result["accounts"]["working"]["pending"] == 1
    assert result["warnings"] == ["Temporary outage."]


def test_chronology_across_accounts_suppresses_older_decisions(tmp_path, monkeypatch):
    engine = _seed()
    accounts = {
        key: {
            "id": key,
            "provider": "microsoft",
            "email": key + "@example.com",
            "token": {
                "access_token": "secret",
                "refresh_token": "refresh",
                "expires_at": 9999999999,
            },
        }
        for key in ["new", "old"]
    }
    store.write_accounts(accounts, tmp_path)

    def read(account, cursor, **_transport):
        return (
            [
                message(
                    "same-id",
                    9000 if account["id"] == "new" else 1000,
                    "rejection" if account["id"] == "new" else "interview",
                )
            ],
            {"delta": "done"},
            False,
        )

    monkeypatch.setattr(microsoft, "read_page", read)
    for key in ["old", "new", "old"]:
        mailboxes.run_mailbox_sync(
            engine,
            Mock(),
            account_id=key,
            data_dir=tmp_path,
            settings=Settings(gmail_max_ai_calls=0),
        )
    with Session(engine) as session:
        pending = session.exec(
            select(Notification).where(Notification.state == "pending")
        ).all()
        assert len(pending) == 1 and pending[0].proposed_status == "rejected"
        application = session.get(Application, 1)
        assert application and application.status == "submitted"
