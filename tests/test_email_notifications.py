import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from resume_tailor_harness.api.schemas.email_notifications import (
    EmailNotificationUpdate,
)
from resume_tailor_harness.config import Settings
from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.mail.mailer import MailDeliveryError
from resume_tailor_harness.mail.tables import EmailNotificationPreference as Preference
from resume_tailor_harness.services import email_notifications as service
from resume_tailor_harness.tracking.tables import Application, ApplicationEvent, Job


NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
SETTINGS = Settings(
    _env_file=None,
    resend_api_key="test-key",
    mail_from="test@example.com",
    app_base_url="https://app.example.com",
    session_secret="test-secret",
)


class Mailbox:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, **message):
        self.sent.append(message)
        if self.fail:
            raise MailDeliveryError("offline")

    def notify(self, **message):
        self.send(**message)


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'workspace.db'}")
    init_db(engine)
    yield engine
    engine.dispose()


def values(**overrides):
    return EmailNotificationUpdate(
        **{
            "email": "user@example.com",
            "enabled": True,
            "frequency": "daily",
            **overrides,
        }
    ).model_dump()


def request_code(engine, box, *, now=NOW):
    service.request_verification(engine, box, SETTINGS, now=now)
    return re.search(r"\b([0-9]{6})\b", box.sent[-1]["body"])[1]


def subscribe(engine, box, **overrides):
    service.update_preference(engine, values(**overrides), now=NOW)
    code = request_code(engine, box)
    service.verify_address(engine, "user@example.com", code, SETTINGS, now=NOW)
    box.sent.clear()


def test_requires_verification_and_delivers_only_at_selected_interval(engine):
    box = Mailbox()
    service.update_preference(engine, values(), now=NOW)
    assert not service.deliver_due(
        engine, box, SETTINGS, "owner", now=NOW + timedelta(days=2)
    )
    code = request_code(engine, box)
    assert code not in service.get_preference(engine).code_hash
    row = service.verify_address(engine, "USER@example.com", code, SETTINGS, now=NOW)
    assert service.utc(row.next_send_at) == NOW + timedelta(days=1)
    with pytest.raises(service.NotificationError):
        service.verify_address(engine, row.email, code, SETTINGS, now=NOW)
    box.sent.clear()
    assert not service.deliver_due(engine, box, SETTINGS, "owner", now=NOW)
    assert service.deliver_due(
        engine, box, SETTINGS, "owner", now=NOW + timedelta(days=1)
    )
    assert not service.deliver_due(
        engine, box, SETTINGS, "owner", now=NOW + timedelta(days=1)
    )
    assert len(box.sent) == 1
    assert "List-Unsubscribe-Post" in box.sent[0]["headers"]


@pytest.mark.parametrize(
    "frequency,days", [("daily", 1), ("weekly", 7), ("monthly", 30)]
)
def test_frequency_reschedules_and_verified_opt_back_in_does_not_require_new_code(
    engine, frequency, days
):
    box = Mailbox()
    subscribe(engine, box)
    token = service.get_preference(engine).unsubscribe_token
    assert service.unsubscribe(engine, token)
    assert not service.deliver_due(
        engine, box, SETTINGS, "owner", now=NOW + timedelta(days=100)
    )
    row = service.update_preference(engine, values(frequency=frequency), now=NOW)
    assert row.verified_at is not None
    assert service.utc(row.next_send_at) == NOW + timedelta(days=days)


def test_changed_email_invalidates_verification_code_and_unsubscribe_link(engine):
    box = Mailbox()
    subscribe(engine, box)
    token = service.get_preference(engine).unsubscribe_token
    row = service.update_preference(engine, values(email="other@example.com"), now=NOW)
    assert row.verified_at is None and row.next_send_at is None
    assert not service.unsubscribe(engine, token)
    assert not service.deliver_due(
        engine, box, SETTINGS, "owner", now=NOW + timedelta(days=10)
    )


def test_verification_attempts_expiry_and_resend_budget_survive_new_sessions(engine):
    box = Mailbox()
    service.update_preference(engine, values(), now=NOW)
    code = request_code(engine, box)
    wrong = "999999" if code != "999999" else "111111"
    for _ in range(5):
        with pytest.raises(service.NotificationError):
            service.verify_address(engine, "user@example.com", wrong, SETTINGS, now=NOW)
    with pytest.raises(service.NotificationError):
        service.verify_address(engine, "user@example.com", code, SETTINGS, now=NOW)
    with pytest.raises(service.NotificationError, match="wait"):
        request_code(engine, box)
    code = request_code(engine, box, now=NOW + timedelta(minutes=1))
    with pytest.raises(service.NotificationError):
        service.verify_address(
            engine, "user@example.com", code, SETTINGS, now=NOW + timedelta(minutes=16)
        )
    request_code(engine, box, now=NOW + timedelta(minutes=17))
    service.update_preference(engine, values(email="other@example.com"), now=NOW)
    with pytest.raises(service.NotificationError, match="wait"):
        request_code(engine, box, now=NOW + timedelta(minutes=18))


def test_failed_verification_mail_cannot_be_used_and_unconfigured_mail_is_not_success(
    engine,
):
    box = Mailbox()
    service.update_preference(engine, values(), now=NOW)
    with pytest.raises(service.NotificationError):
        service.request_verification(
            engine, box, SETTINGS.model_copy(update={"app_base_url": ""}), now=NOW
        )
    assert box.sent == []
    box.fail = True
    with pytest.raises(service.NotificationError):
        request_code(engine, box)
    assert service.get_preference(engine).code_hash == ""


def test_digest_filters_content_escapes_html_and_uses_current_reminders(engine):
    box = Mailbox()
    subscribe(engine, box, frequency="weekly")
    due = NOW + timedelta(days=7)
    with Session(engine) as session:
        visible = Job(
            source="test",
            title="Engineer <script>alert(1)</script>",
            company="A & B",
            status="shortlisted",
        )
        hidden = Job(
            source="test", title="Hidden", status="shortlisted", archived_at=NOW
        )
        session.add_all([visible, hidden])
        session.commit()
        session.refresh(visible)
        application = Application(
            job_id=visible.id,
            status="interview",
            submitted_at=NOW,
            updated_at=NOW - timedelta(days=60),
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        session.add_all(
            [
                ApplicationEvent(
                    application_id=application.id,
                    kind="technical_round",
                    occurred_at=due + timedelta(days=2),
                ),
                ApplicationEvent(
                    application_id=application.id,
                    kind="offer_deadline",
                    occurred_at=due - timedelta(days=1),
                ),
                ApplicationEvent(
                    application_id=application.id,
                    kind="offer_deadline",
                    occurred_at=due + timedelta(days=1),
                    result="cancelled",
                ),
            ]
        )
        session.commit()
    assert service.deliver_due(engine, box, SETTINGS, "owner", now=due)
    message = box.sent[-1]
    assert "1 jobs awaiting review" in message["body"]
    assert "Hidden" not in message["body"]
    assert "1 applications submitted" in message["body"]
    assert "Interview / assessment" in message["body"]
    assert "Follow up after" in message["body"]
    assert "Offer deadline" not in message["body"]
    assert "<script>" not in message["html"]
    assert "&lt;script&gt;" in message["html"]


def test_disabled_topics_and_empty_digest_are_skipped(engine):
    box = Mailbox()
    subscribe(engine, box, statistics=False, reminders=False)
    assert not service.deliver_due(
        engine, box, SETTINGS, "owner", now=NOW + timedelta(days=1)
    )
    with Session(engine) as session:
        session.add(Job(source="test", title="Engineer", status="shortlisted"))
        session.commit()
    assert service.deliver_due(
        engine, box, SETTINGS, "owner", now=NOW + timedelta(days=2)
    )
    assert "Workspace statistics" not in box.sent[0]["body"]
    assert "Reminders" not in box.sent[0]["body"]


def test_retry_keeps_exact_payload_and_opt_out_clears_it(engine):
    box = Mailbox()
    subscribe(engine, box)
    due = NOW + timedelta(days=1)
    box.fail = True
    assert not service.deliver_due(engine, box, SETTINGS, "owner", now=due)
    assert not service.deliver_due(
        engine, box, SETTINGS, "owner", now=due + timedelta(minutes=1)
    )
    row = service.get_preference(engine)
    assert row.last_sent_at is None and row.delivery_failures == 1
    # Another scheduler instance uses persisted state and the same provider key.
    box.fail = False
    assert service.deliver_due(
        engine, box, SETTINGS, "owner", now=due + timedelta(hours=1)
    )
    assert box.sent[0] == box.sent[1]
    box.fail = True
    service.deliver_due(engine, box, SETTINGS, "owner", now=due + timedelta(days=2))
    assert service.unsubscribe(engine, row.unsubscribe_token)
    assert not service.get_preference(engine).pending_payload
    assert not service.deliver_due(
        engine, box, SETTINGS, "owner", now=due + timedelta(days=3)
    )


def test_parallel_schedulers_send_once(engine):
    box = Mailbox()
    subscribe(engine, box)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: service.deliver_due(
                    engine, box, SETTINGS, "owner", now=NOW + timedelta(days=1)
                ),
                range(2),
            )
        )
    assert sorted(results) == [False, True]
    assert len(box.sent) == 1


def test_stale_uncertain_delivery_is_retired_before_provider_idempotency_expires(
    engine,
):
    box = Mailbox()
    subscribe(engine, box)
    box.fail = True
    due = NOW + timedelta(days=1)
    service.deliver_due(engine, box, SETTINGS, "owner", now=due)
    box.fail = False
    assert not service.deliver_due(
        engine, box, SETTINGS, "owner", now=due + timedelta(hours=13)
    )
    assert len(box.sent) == 1
    assert service.get_preference(engine).pending_payload == ""


def test_workspace_schema_upgrade_is_idempotent(engine):
    init_db(engine)
    with Session(engine) as session:
        assert session.get(Preference, 1) is None


@pytest.mark.parametrize("state", ["accepted", "dismissed", "cleared", "pending"])
def test_digest_respects_followup_episode_state(engine, state):
    from resume_tailor_harness.services.reminders import follow_up_key
    from resume_tailor_harness.tracking.tables import Notification

    anchor = NOW - timedelta(days=60)
    with Session(engine) as session:
        job = Job(source="test", title="Follow-up job")
        session.add(job)
        session.commit()
        app = Application(job_id=job.id, status="submitted", updated_at=anchor)
        session.add(app)
        session.commit()
        session.add(
            Notification(
                application_id=app.id,
                kind="follow_up",
                state=state,
                proposed_status="",
                evidence="",
                message_id=follow_up_key(app.id, anchor),
            )
        )
        session.commit()
        context = service._digest_context(session, Preference(), SETTINGS, NOW)
        assert bool(context["reminder_items"]) == (state == "pending")
        app.updated_at = anchor + timedelta(days=1)
        session.add(app)
        session.commit()
        assert service._digest_context(session, Preference(), SETTINGS, NOW)[
            "reminder_items"
        ]


def test_resolved_followups_do_not_fill_digest_limit(engine):
    from resume_tailor_harness.services.reminders import follow_up_key
    from resume_tailor_harness.tracking.tables import Notification

    with Session(engine) as session:
        for index in range(11):
            anchor = NOW - timedelta(days=60 - index)
            job = Job(source="test", title=f"Job {index}")
            session.add(job)
            session.commit()
            app = Application(job_id=job.id, status="submitted", updated_at=anchor)
            session.add(app)
            session.commit()
            if index < 10:
                session.add(
                    Notification(
                        application_id=app.id,
                        kind="follow_up",
                        state="dismissed",
                        proposed_status="",
                        evidence="",
                        message_id=follow_up_key(app.id, anchor),
                    )
                )
                session.commit()
        items = service._digest_context(session, Preference(), SETTINGS, NOW)[
            "reminder_items"
        ]
        assert len(items) == 1
        assert "Job 10" in items[0]
