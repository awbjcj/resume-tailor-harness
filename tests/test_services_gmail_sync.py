from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.gmail.errors import GmailNotConnected
from resume_tailor_harness.progress import ProgressReporter
from resume_tailor_harness.services.gmail_sync import run_gmail_sync
from resume_tailor_harness.tracking.repository import save_application, save_job
from resume_tailor_harness.tracking.tables import Application, Job


class _FakeRequest:
    def __init__(self, result: dict[str, object]):
        self.result = result

    def execute(self, **kwargs) -> dict[str, object]:
        return self.result


class _FakeListing:
    def __init__(self, messages):
        self._messages = messages
        self.gets: list[tuple[str, str]] = []
        self.list_calls = 0

    def list(self, **kwargs):
        self.list_calls += 1
        start = int(kwargs.get("pageToken", "0"))
        end = start + kwargs["maxResults"]
        refs = [{"id": m["id"]} for m in self._messages[start:end]]
        result: dict[str, object] = {"messages": refs}
        if end < len(self._messages):
            result["nextPageToken"] = str(end)
        return _FakeRequest(result)

    def get(self, userId, id, format, metadataHeaders=None):
        self.gets.append((id, format))
        msg = next(m for m in self._messages if m["id"] == id)
        if format == "full":
            result = {"payload": msg.get("payload", {})}
        else:
            result = {
                "payload": {"headers": msg["headers"]},
                "snippet": msg.get("snippet", ""),
                "threadId": msg.get("threadId"),
                "internalDate": msg.get("internalDate", "0"),
                "labelIds": msg.get("labelIds", ["INBOX"]),
            }
        return _FakeRequest(result)


class FakeGmailService:
    def __init__(self, messages):
        self._messages = _FakeListing(messages)
        self.history_id = "1"
        self.mailbox = "test@example.com"
        self.history_pages: list[dict] = []
        self.batch_sizes: list[int] = []
        self.profile_reads = 0
        self.history_reads = 0

    def users(self):
        return self

    def messages(self):
        return self._messages

    def getProfile(self, **kwargs):
        self.profile_reads += 1
        return _FakeRequest(
            {"emailAddress": self.mailbox, "historyId": self.history_id}
        )

    def history(self):
        return self

    def list(self, **kwargs):
        self.history_reads += 1
        index = int(kwargs.get("pageToken", "0"))
        return _FakeRequest(
            self.history_pages[index]
            if self.history_pages
            else {"historyId": self.history_id}
        )

    def new_batch_http_request(self, callback):
        sizes = self.batch_sizes

        class Batch:
            def __init__(self):
                self.requests = []

            def add(self, request, request_id):
                self.requests.append((request_id, request))

            def execute(self):
                sizes.append(len(self.requests))
                for request_id, request in self.requests:
                    try:
                        result = request.execute()
                    except Exception as exc:
                        callback(request_id, None, exc)
                    else:
                        callback(request_id, result, None)

        return Batch()


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
    assert result["stats"]["matched"] >= 1
    assert not result["has_more"]


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
    assert (
        "AI classification is unavailable. Synced using email rules only."
        in result["warnings"]
    )
    assert factory.call_count == 1
    assert runner.run.call_count == (1 if fail_at == "classify" else 0)
    with Session(engine) as session:
        notifications = pending_notifications(session)
        assert notifications[0].message_id.endswith(":Gamma")
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
    result = run_gmail_sync(engine, _reporter(tmp_path), service=FakeGmailService([]))
    assert result["pending"] == 0
    assert result["stats"]["processed"] == 0
    assert not result["has_more"]
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


def test_sync_recovers_nvidia_rejection_beyond_inbox_limit(tmp_path):
    """The real failure: 51 ordinary emails hid a role-specific rejection."""
    import base64
    from resume_tailor_harness.tracking.repository import pending_notifications

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        for ref in ("JR2018181", "JR2025254"):
            job = save_job(
                session,
                Job(
                    source="workday",
                    company="NVIDIA",
                    title="Senior Applied AI Engineer",
                    url=f"https://nvidia.wd5.myworkdayjobs.com/jobs/Engineer_{ref}",
                ),
            )
            assert job.id is not None
            app = save_application(
                session, Application(job_id=job.id, status="submitted")
            )
        target_id = app.id
    body = (
        "<p>We have reviewed your application and have decided not to move forward "
        "for the JR2025254 Senior Applied AI Engineer role at this time.</p>"
    )
    rejection = {
        "id": "nvidia-rejection",
        "headers": [
            {"name": "From", "value": "NVIDIA HR <nvidia@myworkday.com>"},
            {"name": "Subject", "value": "Thank you from NVIDIA"},
        ],
        "snippet": "Thank you for your interest in working at NVIDIA.",
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
                }
            ],
        },
    }
    ordinary = [
        {"id": str(i), "headers": [], "snippet": "Daily newsletter"} for i in range(51)
    ]

    class Listing(_FakeListing):
        def list(self, **kwargs):
            candidates = (
                ordinary + [rejection] if kwargs.get("labelIds") else [rejection]
            )
            start = int(kwargs.get("pageToken", "0"))
            end = start + kwargs["maxResults"]
            refs = [{"id": m["id"]} for m in candidates[start:end]]
            result: dict[str, object] = {"messages": refs}
            if len(candidates) > end:
                result["nextPageToken"] = str(end)
            return _FakeRequest(result)

    service = FakeGmailService([])
    service._messages = Listing(ordinary + [rejection])
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert result["pending"] == 1
    with Session(engine) as session:
        notice = pending_notifications(session)[0]
        assert notice.application_id == target_id
        assert notice.proposed_status == "rejected"
        assert notice.message_id.endswith(":nvidia-rejection")
        assert all(
            a.status == "submitted" for a in session.exec(select(Application)).all()
        )
    assert (
        run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)[
            "pending"
        ]
        == 1
    )
