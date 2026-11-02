import pytest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

from sqlmodel import Session, col, select

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.services.notifications import (
    accept_notification,
    dismiss_notification,
    list_pending,
    sync_notifications,
    notification_revision,
    NotificationConflictError,
)
from resume_tailor_harness.services.application_events import EventValidationError
from resume_tailor_harness.tracking.repository import (
    get_application,
    save_application,
    save_job,
)
from resume_tailor_harness.tracking.tables import Application, ApplicationEvent, Job, Notification


def _seed(session: Session):
    job = save_job(session, Job(source="manual", company="Acme", title="Eng"))
    assert job.id is not None
    app = save_application(session, Application(job_id=job.id, status="submitted"))
    return app


def _email(message_id: str) -> EmailMessage:
    return EmailMessage(
        sender="recruiting@acme.com",
        sender_domain="acme.com",
        subject="Interview at Acme",
        snippet="Schedule a call",
        message_id=message_id,
    )


def test_sync_creates_pending_and_is_idempotent():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        _seed(session)
        first = sync_notifications(
            session, [_email("m1")], classify=lambda email: "interview"
        )
        again = sync_notifications(
            session, [_email("m1")], classify=lambda email: "interview"
        )

        assert len(first) == 1
        assert len(again) == 1
        assert again[0].message_id == "m1"


def test_accept_applies_transition_and_dismiss_suppresses():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        app = _seed(session)
        assert app.id is not None
        [notification] = sync_notifications(
            session, [_email("m1")], classify=lambda email: "interview"
        )
        assert notification.id is not None
        accepted = accept_notification(session, notification.id)

        assert accepted is not None
        assert accepted.state == "accepted"
        updated = get_application(session, app.id)
        assert updated is not None
        assert updated.status == "interview"

        [second] = sync_notifications(
            session, [_email("m2")], classify=lambda email: "offer"
        )
        assert second.id is not None
        dismissed = dismiss_notification(session, second.id)
        assert dismissed is not None
        sync_notifications(session, [_email("m2")], classify=lambda email: "offer")
        assert all(item.message_id != "m2" for item in list_pending(session))


@pytest.mark.parametrize("current", ["offer", "rejected", "closed"])
def test_accept_cannot_regress_an_application_that_advanced_since_sync(current):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        app = _seed(session)
        [notification] = sync_notifications(session, [_email("m1")])
        app.status = current
        session.add(app)
        session.commit()
        assert notification.id is not None
        assert accept_notification(session, notification.id) is not None
        session.refresh(app)
        assert app.status == current


def test_accept_rechecks_pending_state_even_when_session_has_stale_object():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        app = _seed(session)
        [notification] = sync_notifications(session, [_email("m1")])
        assert notification.id is not None
        assert notification.state == "pending"
        with Session(engine) as other:
            from resume_tailor_harness.tracking.tables import Notification

            newer = other.get(Notification, notification.id)
            assert newer is not None
            newer.state = "superseded"
            other.add(newer)
            other.commit()
        assert accept_notification(session, notification.id) is None
        session.refresh(app)
        assert app.status == "submitted"


def _event_payload(**overrides):
    return {
        "kind": "technical_round",
        "occurred_at": datetime(2026, 11, 6, 19, tzinfo=timezone.utc),
        "all_day": False,
        "timezone": "America/New_York",
        **overrides,
    }


def _accept_event(session: Session, notification: Notification, **overrides):
    assert notification.id is not None
    return accept_notification(
        session,
        notification.id,
        event=_event_payload(**overrides),
        expected_revision=notification_revision(notification),
        event_details_confirmed=True,
    )


def test_accept_confirmed_event_keeps_evidence_and_is_repeat_safe():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        app = _seed(session)
        [notification] = sync_notifications(session, [_email("mailbox:account-1:m1")])
        assert notification.id is not None
        accepted = _accept_event(session, notification, notes="Ask about the team")
        assert accepted is not None and accepted.state == "accepted"
        [event] = session.exec(select(ApplicationEvent)).all()
        assert event.application_id == app.id
        assert event.kind == "technical_round"
        assert event.occurred_at == datetime(2026, 11, 6, 19)
        assert event.timezone == "America/New_York"
        assert event.source == "mailbox"
        assert "Ask about the team" in (event.notes or "")
        assert notification.evidence in (event.notes or "")
        assert "mailbox:account-1:m1" in (event.notes or "")
        session.refresh(app)
        assert app.status == "interview"
        assert _accept_event(session, notification) is None
        assert dismiss_notification(session, notification.id) is None
        assert len(session.exec(select(ApplicationEvent)).all()) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"occurred_at": None},
        {"occurred_at": datetime(2026, 11, 6, 19)},
        {"timezone": None},
        {"timezone": "Mars/Olympus"},
        {"platform": "other"},
        {"kind": "offer_received"},
    ],
)
def test_invalid_event_rolls_back_the_proposal_and_status(overrides):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        app = _seed(session)
        [notification] = sync_notifications(session, [_email("m1")])
        with pytest.raises(EventValidationError):
            _accept_event(session, notification, **overrides)
        session.refresh(notification)
        session.refresh(app)
        assert notification.state == "pending"
        assert app.status == "submitted"
        assert session.exec(select(ApplicationEvent)).all() == []


@pytest.mark.parametrize("current", ["interview", "offer", "rejected", "closed"])
def test_event_accept_rejects_a_status_that_changed_since_review(current):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        app = _seed(session)
        [notification] = sync_notifications(session, [_email("m1")])
        app.status = current
        session.add(app)
        session.commit()
        with pytest.raises(NotificationConflictError, match="application status changed"):
            _accept_event(session, notification)
        session.refresh(notification)
        session.refresh(app)
        assert notification.state == "pending"
        assert app.status == current
        assert session.exec(select(ApplicationEvent)).all() == []


def test_event_accept_rejects_corrected_evidence_even_with_a_cached_notification():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        app = _seed(session)
        [notification] = sync_notifications(session, [_email("m1")])
        revision = notification_revision(notification)
        assert notification.id is not None
        with Session(engine) as other:
            corrected = other.get(Notification, notification.id)
            assert corrected is not None
            corrected.evidence = "Corrected: choose an interview time"
            other.add(corrected)
            other.commit()
        with pytest.raises(NotificationConflictError, match="update changed"):
            accept_notification(
                session,
                notification.id,
                event=_event_payload(),
                expected_revision=revision,
                event_details_confirmed=True,
            )
        session.refresh(notification)
        session.refresh(app)
        assert notification.state == "pending"
        assert app.status == "submitted"
        assert session.exec(select(ApplicationEvent)).all() == []


def test_event_accept_requires_explicit_confirmation():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        _seed(session)
        [notification] = sync_notifications(session, [_email("m1")])
        assert notification.id is not None
        with pytest.raises(EventValidationError, match="Confirm the timeline"):
            accept_notification(
                session, notification.id, event=_event_payload(),
                expected_revision=notification_revision(notification),
            )
        session.refresh(notification)
        assert notification.state == "pending"


def test_concurrent_accepts_create_one_event_and_one_acceptance(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'notifications.db').as_posix()}")
    init_db(engine)
    with Session(engine) as session:
        _seed(session)
        [notification] = sync_notifications(session, [_email("m1")])
        notification_id = notification.id
        assert notification_id is not None
        revision = notification_revision(notification)
    barrier = Barrier(2)

    def accept_once(_index: int) -> bool:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            return accept_notification(
                session, notification_id, event=_event_payload(),
                expected_revision=revision, event_details_confirmed=True,
            ) is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept_once, range(2))) == [False, True]
    with Session(engine) as session:
        assert len(session.exec(select(ApplicationEvent)).all()) == 1
        assert len(session.exec(select(Notification).where(Notification.state == "accepted")).all()) == 1


def test_same_provider_message_id_in_two_mailboxes_keeps_separate_evidence():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        first_app = _seed(session)
        job = save_job(session, Job(source="manual", company="Beta", title="Eng"))
        assert job.id is not None and first_app.id is not None
        second_app = save_application(session, Application(job_id=job.id, status="submitted"))
        assert second_app.id is not None
        for app_id, account in [(first_app.id, "account-a"), (second_app.id, "account-b")]:
            notice = Notification(
                application_id=app_id, kind="interview", proposed_status="interview",
                evidence=f"Interview from {account}", message_id=f"mailbox:{account}:same-id",
            )
            session.add(notice)
            session.commit()
            assert _accept_event(session, notice) is not None
        events = session.exec(select(ApplicationEvent).order_by(col(ApplicationEvent.id))).all()
        assert len(events) == 2
        assert "mailbox:account-a:same-id" in (events[0].notes or "")
        assert "mailbox:account-b:same-id" in (events[1].notes or "")
