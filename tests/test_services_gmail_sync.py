from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.gmail.errors import GmailNotConnected
from resume_tailor_harness.progress import ProgressReporter
from resume_tailor_harness.services.gmail_sync import run_gmail_sync
from resume_tailor_harness.tracking.repository import save_application, save_job
from resume_tailor_harness.tracking.tables import Application, Job


class _FakeListing:
    def __init__(self, messages):
        self._messages = messages

    def list(self, **kwargs):
        refs = [{"id": m["id"]} for m in self._messages]
        return type(
            "Req", (), {"execute": staticmethod(lambda **_: {"messages": refs})}
        )()

    def get(self, userId, id, format, metadataHeaders=None):
        msg = next(m for m in self._messages if m["id"] == id)
        if format == "full":
            result = {"payload": msg.get("payload", {})}
        else:
            result = {
                "payload": {"headers": msg["headers"]},
                "snippet": msg.get("snippet", ""),
                "threadId": msg.get("threadId"),
            }
        return type("Req", (), {"execute": staticmethod(lambda **_: result)})()


class FakeGmailService:
    def __init__(self, messages):
        self._messages = _FakeListing(messages)

    def users(self):
        messages = self._messages
        return type("Users", (), {"messages": staticmethod(lambda: messages)})()


def _reporter(tmp_path):
    return ProgressReporter("test-run", root=tmp_path)


def test_run_gmail_sync_creates_notifications_without_owning_reminders(tmp_path):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        job = save_job(session, Job(source="manual", company="Acme", title="Eng"))
        assert job.id is not None
        app = save_application(session, Application(job_id=job.id, status="submitted"))
        app.updated_at = datetime.now(timezone.utc) - timedelta(days=30)
        session.add(app)
        session.commit()

    service = FakeGmailService(
        [
            {
                "id": "m1",
                "headers": [
                    {"name": "From", "value": "hr@acme.com"},
                    {"name": "Subject", "value": "Interview at Acme"},
                ],
                "snippet": "Schedule a call",
                "threadId": "t1",
            }
        ]
    )
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert result["pending"] >= 1
    assert set(result) == {"pending"}


def test_run_gmail_sync_disconnected_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolate from a real legacy data/gmail_token.json
    engine = make_engine("sqlite://")
    init_db(engine)
    with pytest.raises(GmailNotConnected):
        run_gmail_sync(engine, _reporter(tmp_path))


@pytest.mark.parametrize("fail_at", ["build", "classify"])
def test_optional_ai_failure_preserves_rule_proposals(tmp_path, monkeypatch, fail_at):
    from unittest.mock import Mock
    from resume_tailor_harness.services import gmail_sync
    from resume_tailor_harness.tracking.repository import pending_notifications

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        for company in ("Acme", "Beta", "Gamma"):
            job = save_job(session, Job(source="manual", company=company, title="Eng"))
            assert job.id is not None
            save_application(session, Application(job_id=job.id, status="submitted"))
    service = FakeGmailService(
        [
            {
                "id": company,
                "headers": [
                    {"name": "From", "value": f"hr@{company.lower()}.com"},
                    {"name": "Subject", "value": subject},
                ],
            }
            for company, subject in [
                ("Acme", "Application update"),
                ("Beta", "Application update"),
                ("Gamma", "Interview"),
            ]
        ]
    )
    runner = Mock()
    runner.run.side_effect = RuntimeError("provider unavailable")
    factory = Mock(return_value=runner)
    if fail_at == "build":
        factory.side_effect = RuntimeError("no model available")
    monkeypatch.setattr(gmail_sync, "build_classifier_llm", factory)
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service)
    assert result["pending"] == 1
    assert result["warnings"] == [
        "AI classification is unavailable. Synced using email rules only."
    ]
    assert factory.call_count == 1
    assert runner.run.call_count == (1 if fail_at == "classify" else 0)
    with Session(engine) as session:
        notifications = pending_notifications(session)
        assert notifications[0].message_id == "Gamma"
        application = session.get(Application, notifications[0].application_id)
        assert application is not None
        assert application.status == "submitted"
    # Repeated passes cannot duplicate the same proposal.
    assert (
        run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)[
            "pending"
        ]
        == 1
    )


def test_empty_inbox_does_not_build_ai(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from resume_tailor_harness.services import gmail_sync

    engine = make_engine("sqlite://")
    init_db(engine)
    factory = Mock(side_effect=AssertionError("AI should not be needed"))
    monkeypatch.setattr(gmail_sync, "build_classifier_llm", factory)
    assert run_gmail_sync(
        engine, _reporter(tmp_path), service=FakeGmailService([])
    ) == {"pending": 0}
    factory.assert_not_called()


def test_cancellation_during_scan_remains_cancellation(tmp_path):
    from resume_tailor_harness.api.runs.manager import RunCancelled

    class CancelledReporter(ProgressReporter):
        def checkpoint(self):
            raise RunCancelled

    with pytest.raises(RunCancelled):
        run_gmail_sync(
            None,
            CancelledReporter("cancelled", root=tmp_path),
            service=FakeGmailService([]),
            llm=None,
        )


def test_sync_honors_configured_data_dir(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from resume_tailor_harness.services import gmail_sync

    engine = make_engine("sqlite://")
    init_db(engine)
    build = Mock(return_value=FakeGmailService([]))
    monkeypatch.setattr(gmail_sync, "build_service", build)
    run_gmail_sync(engine, _reporter(tmp_path), data_dir=tmp_path, llm=None)
    build.assert_called_once_with(tmp_path)
