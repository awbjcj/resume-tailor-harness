import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_tailor_harness.config import Settings
from resume_tailor_harness.mail.account_notifications import (
    deliver_account_emails,
    enqueue_account_email,
    release_deletion_notices,
)
from resume_tailor_harness.mail.mailer import (
    MailDeliveryError,
    ResendMailer,
    SmtpMailer,
)
from resume_tailor_harness.tenancy.quotas import (
    InsufficientCreditError,
    change_tier,
    charge_shared_cost,
    create_operation_preview,
    debit_credit,
    execute_operation,
    grant_credit,
    quota_snapshot,
    reset_current_period,
)
from resume_tailor_harness.tenancy.subscriptions import apply_subscription
from resume_tailor_harness.tenancy.system_db import (
    AccountEmail,
    User,
    init_system_db,
    make_system_engine,
)

USER = "alice0000000"
SETTINGS = Settings(
    _env_file=None, resend_api_key="test", app_base_url="https://app.example.com"
)


class Mailbox:
    def __init__(self):
        self.messages = []
        self.fail = False

    def send(self, **message):
        self.messages.append(message)
        if self.fail:
            raise MailDeliveryError("offline")


@pytest.fixture
def engine(tmp_path):
    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    with Session(engine) as session:
        session.add(
            User(
                id=USER,
                username="Alice <script>alert(1)</script>",
                password_hash="hash",
                email="alice@example.com",
                email_verified_at=datetime.now(UTC),
            )
        )
        session.commit()
    yield engine
    engine.dispose()


def notices(engine):
    with Session(engine) as session:
        return [
            json.loads(row.context_json)
            for row in session.scalars(select(AccountEmail))
        ]


def enqueue(engine, event="account_updated", **kwargs):
    with Session(engine) as session:
        row = enqueue_account_email(session, session.get(User, USER), event, **kwargs)
        session.commit()
        return row.id if row else None


def test_transaction_rollback_and_unverified_addresses_stay_silent(engine):
    with Session(engine) as session:
        user = session.get(User, USER)
        enqueue_account_email(session, user, "account_deleted")
        session.rollback()
        user = session.get(User, USER)
        user.email_verified_at = None
        assert enqueue_account_email(session, user, "account_updated") is None
        user.email = None
        assert enqueue_account_email(session, user, "account_updated") is None
        session.commit()
    assert notices(engine) == []


def test_payload_is_jinja_escaped_and_uses_registered_address_even_after_deletion(
    engine,
):
    enqueue(
        engine, "account_deleted", details={"Reason": "<img src=x onerror=alert(1)>"}
    )
    with Session(engine) as session:
        session.delete(session.get(User, USER))
        session.commit()
    mailbox = Mailbox()
    assert deliver_account_emails(engine, mailbox, SETTINGS) == 1
    message = mailbox.messages[0]
    assert message["to"] == "alice@example.com"
    assert "<script>" in message["body"]
    assert "<script>" not in message["html"]
    assert "&lt;script&gt;" in message["html"]
    assert "<img" not in message["html"]
    assert 'href="https://app.example.com/account"' in message["html"]
    assert deliver_account_emails(engine, mailbox, SETTINGS) == 0


def test_failure_survives_new_session_and_retries_identical_payload(engine):
    row_id = enqueue(engine)
    now = datetime.now(UTC) + timedelta(seconds=1)
    mailbox = Mailbox()
    mailbox.fail = True
    assert deliver_account_emails(engine, mailbox, SETTINGS, now=now) == 0
    assert (
        deliver_account_emails(
            engine, mailbox, SETTINGS, now=now + timedelta(minutes=1)
        )
        == 0
    )
    with Session(engine) as session:
        assert session.get(AccountEmail, row_id).attempts == 1
    mailbox.fail = False
    changed_settings = SETTINGS.model_copy(
        update={"app_base_url": "https://changed.example.com"}
    )
    assert (
        deliver_account_emails(
            engine, mailbox, changed_settings, now=now + timedelta(minutes=3)
        )
        == 1
    )
    assert mailbox.messages[0] == mailbox.messages[1]


def test_worker_lease_prevents_concurrent_delivery_without_holding_writer_lock(engine):
    enqueue(engine)
    entered, release = Event(), Event()

    class BlockingMailbox(Mailbox):
        def send(self, **message):
            entered.set()
            assert release.wait(5)
            super().send(**message)

    mailbox = BlockingMailbox()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(deliver_account_emails, engine, mailbox, SETTINGS)
        try:
            assert entered.wait(5)
            assert deliver_account_emails(engine, mailbox, SETTINGS) == 0
            # A different writer can commit while transport is blocked.
            with Session(engine) as session:
                session.get(User, USER).username = "updated"
                session.commit()
        finally:
            release.set()
        assert first.result(timeout=5) == 1
    assert len(mailbox.messages) == 1


def test_held_and_unconfigured_requests_wait_and_missing_url_still_delivers(engine):
    row_id = enqueue(engine, ready=False)
    mailbox = Mailbox()
    assert deliver_account_emails(engine, mailbox, SETTINGS) == 0
    with Session(engine) as session:
        session.get(AccountEmail, row_id).ready = True
        session.commit()
    assert (
        deliver_account_emails(
            engine,
            mailbox,
            SETTINGS.model_copy(update={"resend_api_key": "", "smtp_host": ""}),
        )
        == 0
    )
    assert (
        deliver_account_emails(
            engine, mailbox, SETTINGS.model_copy(update={"app_base_url": ""})
        )
        == 1
    )
    assert "href=" not in mailbox.messages[0]["html"]


@pytest.mark.parametrize("backend", ["resend", "smtp"])
@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_real_provider_adapters_receive_both_jinja_parts(
    engine, monkeypatch, backend, language
):
    with Session(engine) as session:
        user = session.get(User, USER)
        user.dashboard_language = language
        session.commit()
    enqueue(engine)
    captured = []
    if backend == "resend":

        def handler(request):
            captured.append(json.loads(request.content))
            assert request.headers["Idempotency-Key"].startswith("account-")
            return httpx.Response(200, json={"id": "mail-id"})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            assert (
                deliver_account_emails(engine, ResendMailer(SETTINGS, client), SETTINGS)
                == 1
            )
        assert captured[0]["to"] == ["alice@example.com"]
        assert "text" in captured[0] and "html" in captured[0]
        if language == "zh-CN":
            assert "账户设置已更新" in captured[0]["subject"]
            assert "管理员修改了你的账户设置" in captured[0]["text"]
            assert 'lang="zh-CN"' in captured[0]["html"]
    else:

        class SMTP:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def send_message(self, message):
                captured.append(message)

        monkeypatch.setattr("smtplib.SMTP", SMTP)
        settings = SETTINGS.model_copy(
            update={
                "resend_api_key": "",
                "smtp_host": "smtp.example.com",
                "smtp_username": "",
                "smtp_starttls": False,
            }
        )
        assert deliver_account_emails(engine, SmtpMailer(settings), settings) == 1
        assert captured[0]["To"] == "alice@example.com"
        assert captured[0].get_body(preferencelist=("plain",))
        assert captured[0].get_body(preferencelist=("html",))
        if language == "zh-CN":
            assert "账户设置已更新" in str(captured[0]["Subject"])
            assert (
                "管理员修改了你的账户设置"
                in captured[0].get_body(preferencelist=("plain",)).get_content()
            )
            assert (
                'lang="zh-CN"'
                in captured[0].get_body(preferencelist=("html",)).get_content()
            )


def test_credit_reset_tier_and_automatic_renewal_notices(engine):
    now = datetime.now(UTC)
    grant_credit(engine, USER, 3_000_000, now=now)
    debit_credit(engine, USER, 1_000_000, now=now)
    charge_shared_cost(engine, USER, 100, now=now)
    assert len(notices(engine)) == 2  # Per-call usage does not send email.
    reset_current_period(engine, USER, now=now)
    change_tier(engine, USER, "SUBSCRIBER", now=now)
    quota_snapshot(engine, USER, now=now + timedelta(days=70))
    assert [row["title"] for row in notices(engine)] == [
        "Your credit balance was increased",
        "Your credit balance was decreased",
        "Your quota was reset",
        "Your quota tier was changed",
        "Your quota period was renewed",
    ]


def test_subscription_idempotency_and_expiry_notifications(engine):
    now = datetime.now(UTC)
    kwargs = dict(
        actor_user_id="operator",
        action="ACTIVATE",
        tier_id="SUBSCRIBER",
        cycles=1,
        reason="Paid",
        idempotency_key="activate-once",
        now=now,
    )
    first = apply_subscription(engine, USER, **kwargs)
    assert apply_subscription(engine, USER, **kwargs) == first
    assert len(notices(engine)) == 1
    assert notices(engine)[0]["details"]["Subscription status"] == "ACTIVE"
    apply_subscription(
        engine, USER, **{**kwargs, "action": "RENEW", "idempotency_key": "renew-once"}
    )
    assert notices(engine)[-1]["title"] == "Your subscription was renewed"
    quota_snapshot(engine, USER, now=now + timedelta(days=80))
    assert any(row["title"] == "Your subscription expired" for row in notices(engine))


def test_bulk_operation_notices_are_atomic_and_replay_safe(engine):
    preview = create_operation_preview(
        engine,
        actor_user_id="operator",
        target_type="ALL_MEMBERS",
        target_value=None,
        action_type="GRANT_CREDIT",
        amount_micros=5_000_000,
    )
    kwargs = dict(
        preview_id=preview.id,
        actor_user_id="operator",
        reason="<b>Adjustment</b>",
        idempotency_key="bulk-once",
    )
    execute_operation(engine, **kwargs)
    execute_operation(engine, **kwargs)
    assert len(notices(engine)) == 1
    assert notices(engine)[0]["details"]["Credit balance"] == "USD 5.000000"


def test_bulk_failure_rolls_back_notices_for_previously_processed_members(engine):
    grant_credit(engine, USER, 5_000_000)
    with Session(engine) as session:
        session.add(
            User(
                id="zzzzzzzzzzzz",
                username="second",
                password_hash="hash",
                email="second@example.com",
                email_verified_at=datetime.now(UTC),
            )
        )
        session.commit()
    preview = create_operation_preview(
        engine,
        actor_user_id="operator",
        target_type="ALL_MEMBERS",
        target_value=None,
        action_type="DEBIT_CREDIT",
        amount_micros=1_000_000,
    )
    with pytest.raises(InsufficientCreditError):
        execute_operation(
            engine,
            preview_id=preview.id,
            actor_user_id="operator",
            reason="Debit",
            idempotency_key="bulk-failed",
        )
    assert len(notices(engine)) == 1
    assert quota_snapshot(engine, USER).credit_balance_micros == 5_000_000


def test_crashed_worker_lease_expires_and_request_is_recovered(engine):
    row_id = enqueue(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        row = session.get(AccountEmail, row_id)
        row.lease_until = now + timedelta(minutes=2)
        row.attempts = 1
        session.commit()
    mailbox = Mailbox()
    assert deliver_account_emails(engine, mailbox, SETTINGS, now=now) == 0
    assert (
        deliver_account_emails(
            engine, mailbox, SETTINGS, now=now + timedelta(minutes=3)
        )
        == 1
    )


def test_deletion_release_recovers_only_completed_cleanup(engine, tmp_path):
    row_id = enqueue(engine, "account_deleted", ready=False)
    release_deletion_notices(engine, tmp_path)
    with Session(engine) as session:
        assert session.get(AccountEmail, row_id).ready is False
        session.delete(session.get(User, USER))
        session.commit()
    tombstone = tmp_path / "users" / f".{USER}.deleting-test"
    tombstone.mkdir(parents=True)
    release_deletion_notices(engine, tmp_path)
    with Session(engine) as session:
        assert session.get(AccountEmail, row_id).ready is False
    tombstone.rmdir()
    release_deletion_notices(engine, tmp_path)
    with Session(engine) as session:
        assert session.get(AccountEmail, row_id).ready is True
