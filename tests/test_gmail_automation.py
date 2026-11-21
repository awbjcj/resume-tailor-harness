import base64
from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import Mock

import pytest
from sqlmodel import Session, col, select

from resume_tailor_harness.gmail.automation import preference, set_automation
from resume_tailor_harness.gmail.tables import GmailSyncState
from resume_tailor_harness.services.gmail_sync import run_gmail_sync
from resume_tailor_harness.tracking.tables import (
    Application,
    ApplicationEvent,
    Job,
    Notification,
)
from tests.test_gmail_incremental_sync import _history, _seed
from tests.test_services_gmail_sync import FakeGmailService, _reporter

_ENABLE_TIME = 2_000
_REJECTION = "We have decided to move forward with other candidates."


def _decision(
    mid,
    *,
    text=_REJECTION,
    date=3_000,
    role="R900000",
    sender="employer0.com",
    verifier="mx.google.com",
    verdict="pass",
):
    body = f"Thank you for your application for {role}. {text}"
    return {
        "id": mid,
        "internalDate": str(date),
        "headers": [
            {"name": "From", "value": f"Employer 0 HR <hr@{sender}>"},
            {"name": "Subject", "value": "Application update"},
            {
                "name": "Authentication-Results",
                "value": f"{verifier}; dmarc={verdict} (p=reject) header.from={sender}",
            },
        ],
        "snippet": body,
        "payload": {
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
        },
    }


def _enable(engine, gmail):
    with Session(engine) as session:
        set_automation(session, sha256(gmail.mailbox.encode()).hexdigest())
        settings = preference(session)
        assert settings is not None
        settings.enabled_at = datetime.fromtimestamp(_ENABLE_TIME / 1000, timezone.utc)
        session.commit()


def _sync(engine, tmp_path, gmail):
    return run_gmail_sync(engine, _reporter(tmp_path), service=gmail, llm=None)


def test_applies_only_after_opt_in_and_records_the_email_once(tmp_path):
    engine = _seed(2)
    with Session(engine) as session:
        job = session.get(Job, 1)
        assert job is not None
        job.url = "https://employer0.wd1.myworkdayjobs.com/Search/job/Senior-Engineer_7001000-2"
        job.criteria_json = {
            "manual_details": {
                "application_url": "https://careers.employer0.com/jobs/7001000",
            }
        }
        session.commit()
    gmail = FakeGmailService(
        [_decision("old", date=1_000, role="R900001", sender="employer1.com")]
    )
    assert _sync(engine, tmp_path, gmail)["stats"]["auto_applied"] == 0
    _enable(engine, gmail)
    _history(
        gmail,
        [
            _decision(
                "new",
                role="Senior Engineer position, 7001000",
                sender="hr.employer0.com",
            )
        ],
    )
    assert _sync(engine, tmp_path, gmail)["stats"]["auto_applied"] == 1
    assert _sync(engine, tmp_path, gmail)["stats"]["auto_applied"] == 0
    with Session(engine) as session:
        assert [
            app.status
            for app in session.exec(select(Application).order_by(col(Application.id)))
        ] == ["rejected", "submitted"]
        event = session.exec(select(ApplicationEvent)).one()
        assert event.kind == "rejected" and event.source == "mailbox"
        assert event.notes and "https://mail.google.com/mail/#all/new" in event.notes
        assert {row.state for row in session.exec(select(Notification))} == {
            "accepted",
            "pending",
        }


@pytest.mark.parametrize(
    "overrides",
    [
        {"role": "Senior Engineer"},
        {"sender": "employer0.example.com"},
        {"sender": "employer0.net"},
        {"verifier": "somewhere.example"},
        {"verdict": "fail"},
        {
            "text": "We have decided not to proceed with your application unless the role reopens."
        },
        {"text": "Please schedule an interview."},
    ],
)
def test_inexact_or_unconfirmed_decisions_stay_in_review(tmp_path, overrides):
    engine = _seed()
    gmail = FakeGmailService([_decision("candidate", **overrides)])
    _enable(engine, gmail)
    assert _sync(engine, tmp_path, gmail)["stats"]["auto_applied"] == 0
    with Session(engine) as session:
        assert session.exec(select(Application)).one().status == "submitted"
        assert session.exec(select(Notification)).one().state == "pending"
        assert session.exec(select(ApplicationEvent)).first() is None


def test_shared_board_domain_does_not_establish_employer_ownership(tmp_path):
    engine = _seed()
    with Session(engine) as session:
        job = session.exec(select(Job)).one()
        job.company = "Greenhouse"
        job.url = "https://job-boards.greenhouse.io/greenhouse/jobs/900000"
        session.commit()
    gmail = FakeGmailService(
        [_decision("candidate", sender="greenhouse.io", role="job 900000")]
    )
    _enable(engine, gmail)
    assert _sync(engine, tmp_path, gmail)["stats"]["auto_applied"] == 0
    with Session(engine) as session:
        assert session.exec(select(Notification)).one().state == "pending"


def test_rejection_from_before_a_same_day_submission_stays_in_review(tmp_path):
    engine = _seed()
    with Session(engine) as session:
        app = session.exec(select(Application)).one()
        app.submitted_at = datetime.fromtimestamp(4, timezone.utc)
        session.commit()
    gmail = FakeGmailService([_decision("earlier")])
    _enable(engine, gmail)
    assert _sync(engine, tmp_path, gmail)["stats"]["auto_applied"] == 0
    with Session(engine) as session:
        assert session.exec(select(Application)).one().status == "submitted"
        assert session.exec(select(Notification)).one().state == "pending"


def test_waits_for_a_newer_decision_on_the_next_arrival_page(tmp_path, monkeypatch):
    from resume_tailor_harness.config import Settings
    from resume_tailor_harness.services import gmail_sync

    engine = _seed()
    gmail = FakeGmailService([])
    _sync(engine, tmp_path, gmail)
    _enable(engine, gmail)
    older = _decision("earlier")
    newer = _decision("later", date=4_000, text="Please schedule an interview.")
    _history(gmail, [older, newer])
    gmail.history_pages = [
        {
            "historyId": "2",
            "nextPageToken": "1",
            "history": [{"messagesAdded": [{"message": {"id": "earlier"}}]}],
        },
        {
            "historyId": "2",
            "history": [{"messagesAdded": [{"message": {"id": "later"}}]}],
        },
    ]
    monkeypatch.setattr(
        gmail_sync, "get_settings", lambda: Settings(gmail_sync_max_pages=1)
    )
    first = _sync(engine, tmp_path, gmail)
    assert first["has_more"] and first["stats"]["auto_applied"] == 0
    for _ in range(4):
        result = _sync(engine, tmp_path, gmail)
        assert result["stats"]["auto_applied"] == 0
        if not result["has_more"]:
            break
    else:
        pytest.fail("Gmail arrival pages did not finish")
    with Session(engine) as session:
        assert session.exec(select(Application)).one().status == "submitted"
        notices = {
            row.proposed_status: row.state for row in session.exec(select(Notification))
        }
        assert notices == {"rejected": "superseded", "interview": "pending"}


@pytest.mark.parametrize("expired_history", [False, True])
def test_waits_for_recovered_interview_before_auto_rejecting(
    tmp_path, monkeypatch, expired_history
):
    from resume_tailor_harness.config import Settings
    from resume_tailor_harness.services import gmail_sync
    from tests.test_gmail_client import _error

    engine = _seed()
    gmail = FakeGmailService([])
    _sync(engine, tmp_path, gmail)
    _enable(engine, gmail)
    with Session(engine) as session:
        state = session.exec(select(GmailSyncState)).one()
        state.cursors = {**state.cursors, "next_lane": "history"}
        session.commit()
    newer = _decision("restored", date=4_000, text="Please schedule an interview.")
    _history(gmail, [_decision("earlier")])
    gmail._messages._messages.append(newer)
    gmail.label_history_pages = [
        {
            "historyId": "2",
            "history": [
                {
                    "labelsRemoved": [
                        {"message": {"id": "restored"}, "labelIds": ["TRASH"]}
                    ]
                }
            ],
        }
    ]
    if expired_history:
        original = gmail.list
        expired = False

        def history_list(**kwargs):
            nonlocal expired
            if kwargs["historyTypes"] != ["messageAdded"] and not expired:
                expired = True
                request = Mock()
                request.execute.side_effect = _error(404)
                return request
            return original(**kwargs)

        monkeypatch.setattr(gmail, "list", history_list)

    monkeypatch.setattr(
        gmail_sync,
        "get_settings",
        lambda: Settings(gmail_sync_max_pages=1, gmail_max_messages=1),
    )
    first = _sync(engine, tmp_path, gmail)
    assert first["has_more"] and first["stats"]["auto_applied"] == 0
    with Session(engine) as session:
        assert session.exec(select(Notification)).one().proposed_status == "rejected"
    for _ in range(9):
        result = _sync(engine, tmp_path, gmail)
        assert result["stats"]["auto_applied"] == 0
        if not result["has_more"]:
            break
    else:
        pytest.fail("Gmail recovery queues did not finish")

    with Session(engine) as session:
        assert session.exec(select(Application)).one().status == "submitted"
        assert session.exec(select(ApplicationEvent)).first() is None
        notices = {
            row.proposed_status: row.state for row in session.exec(select(Notification))
        }
        assert notices == {"rejected": "superseded", "interview": "pending"}
