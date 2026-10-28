import base64
from collections import Counter
from unittest.mock import Mock

import pytest
from sqlmodel import Session, select

from resume_tailor_harness.api.runs.manager import RunCancelled
from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.config import Settings
from resume_tailor_harness.gmail.errors import GmailApiError
from resume_tailor_harness.gmail.tables import GmailReceipt, GmailSyncState
from resume_tailor_harness.services.gmail_sync import _sync_lock, run_gmail_sync
from resume_tailor_harness.services.notifications import accept_notification
from resume_tailor_harness.tracking.tables import Application, Job, Notification
from tests.test_gmail_client import _error
from tests.test_services_gmail_sync import FakeGmailService, _reporter


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from resume_tailor_harness.services import gmail_sync

    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setattr(gmail_sync, "get_settings", Settings)


def _seed(count=1):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        for i in range(count):
            job = Job(
                id=i + 1,
                source="manual",
                company=f"Employer {i}",
                title="Senior Engineer",
                url=f"https://employer{i}.com/jobs/R{900000 + i}",
            )
            session.add(job)
            session.add(Application(id=i + 1, job_id=i + 1, status="submitted"))
        session.commit()
    return engine


def _mail(mid, company=0, decision="rejection", date=2000):
    statement = {
        "rejection": "We have decided not to move forward with your application.",
        "interview": "Please schedule an interview with us.",
        "uncertain": "There is an update about your candidacy.",
    }[decision]
    text = f"For R{900000 + company} Senior Engineer: {statement}"
    return {
        "id": mid,
        "internalDate": str(date),
        "headers": [
            {"name": "From", "value": f"HR <hr@employer{company}.com>"},
            {"name": "Subject", "value": "Application update"},
        ],
        "snippet": text,
        "payload": {
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(text.encode()).decode()},
        },
    }


def _history(service, messages):
    service.history_id = str(int(service.history_id) + 1)
    service.history_pages = [
        {
            "historyId": service.history_id,
            "history": [
                {"messagesAdded": [{"message": {"id": message["id"]}}]}
                for message in messages
            ],
        }
    ]
    service._messages._messages = messages + service._messages._messages


@pytest.mark.parametrize("application_count", [500, 5000])
def test_large_mailbox_resumes_without_repeated_downloads_or_stale_proposals(
    tmp_path, monkeypatch, application_count
):
    monkeypatch.setenv("GMAIL_MAX_MESSAGES", "50")
    monkeypatch.setenv("GMAIL_SYNC_MAX_PAGES", "4")
    engine = _seed(application_count)
    # Newer decisions arrive on earlier pages; old invitations arrive in later runs.
    messages = [
        _mail(f"reject-{i}", i, date=20000 + i) for i in range(application_count)
    ] + [
        _mail(f"invite-{i}", i, "interview", date=1000 + i)
        for i in range(application_count)
    ]
    service = FakeGmailService(messages)
    for run in range(application_count // 25 + 3):
        result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
        assert result["stats"]["processed"] <= 200
        if not result["has_more"]:
            break
    else:
        pytest.fail("Backfill never finished")
    assert run > 0
    with Session(engine) as session:
        receipts = session.exec(select(GmailReceipt)).all()
        notices = session.exec(
            select(Notification).where(Notification.state == "pending")
        ).all()
        assert len(receipts) == application_count * 2
        assert len(notices) == application_count
        assert all(n.proposed_status == "rejected" for n in notices)
    counts = Counter(service._messages.gets)
    assert len(counts) == application_count * 4
    assert set(counts.values()) == {1}
    assert max(service.batch_sizes) <= 25
    reads, listings, batches = (
        len(service._messages.gets),
        service._messages.list_calls,
        len(service.batch_sizes),
    )
    idle = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert idle["stats"]["processed"] == 0
    assert idle["stats"]["ai_calls"] == 0
    assert len(service._messages.gets) == reads
    assert service._messages.list_calls == listings
    assert len(service.batch_sizes) == batches


def test_new_history_supersedes_old_pending_and_stale_accept_cannot_apply(tmp_path):
    engine = _seed()
    service = FakeGmailService([_mail("old", decision="interview", date=1000)])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    with Session(engine) as session:
        old_id = session.exec(select(Notification)).one().id
    _history(service, [_mail("new", date=2000)])
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert result["stats"]["metadata_reads"] == 1
    assert result["pending"] == 1
    with Session(engine) as session:
        assert old_id is not None
        old = session.get(Notification, old_id)
        assert old is not None and old.state == "superseded"
        assert accept_notification(session, old_id) is None
        assert session.exec(select(Application)).one().status == "submitted"
        current = session.exec(
            select(Notification).where(Notification.state == "pending")
        ).one()
        assert current.proposed_status == "rejected"


@pytest.mark.parametrize("new_label", ["none", "rejection"])
def test_new_classifier_version_corrects_existing_pending_proposal(
    tmp_path, monkeypatch, new_label
):
    from resume_tailor_harness.gmail import processing
    from resume_tailor_harness.gmail.classify import SyncClassifier

    engine = _seed()
    service = FakeGmailService([_mail("m1", decision="interview")])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    reads = len(service._messages.gets)
    monkeypatch.setattr(processing, "PROCESSING_VERSION", "revised-decisions")
    monkeypatch.setattr(
        SyncClassifier, "classify", lambda self, email: (new_label, False)
    )
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert result["pending"] == (0 if new_label == "none" else 1)
    assert len(service._messages.gets) == reads
    with Session(engine) as session:
        notice = session.exec(select(Notification)).one()
        if new_label == "none":
            assert notice.state == "superseded"
        else:
            assert notice.proposed_status == "rejected"


def test_cancelled_batch_retains_discovered_queue_and_can_resume(tmp_path):
    engine = _seed()
    service = FakeGmailService([_mail("m1")])
    reporter = _reporter(tmp_path)
    original = reporter.checkpoint
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        if calls == 5:  # after page discovery, before receipt/notification commit
            raise RunCancelled
        original()

    reporter.checkpoint = cancel
    with pytest.raises(RunCancelled):
        run_gmail_sync(engine, reporter, service=service, llm=None)
    with Session(engine) as session:
        assert not session.exec(select(GmailReceipt)).all()
        assert session.exec(select(GmailSyncState)).one().cursors["recruiting"][
            "pending"
        ] == ["m1"]
    assert (
        run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)[
            "pending"
        ]
        == 1
    )


def test_history_expiration_restarts_listing_but_reuses_evidence(tmp_path, monkeypatch):
    engine = _seed()
    service = FakeGmailService([_mail("m1")])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    reads = len(service._messages.gets)
    service.history_id = "999"
    request = Mock()
    request.execute.side_effect = _error(404)
    monkeypatch.setattr(service, "list", lambda **kwargs: request)
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert any("history expired" in warning for warning in result["warnings"])
    assert result["pending"] == 1
    assert len(service._messages.gets) == reads


def test_history_page_with_more_messages_than_budget_drops_none(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_MAX_MESSAGES", "2")
    monkeypatch.setenv("GMAIL_SYNC_MAX_PAGES", "2")
    engine = _seed(7)
    service = FakeGmailService([])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    _history(service, [_mail(str(i), i) for i in range(7)])
    first = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert first["has_more"]
    assert first["pending"] == 4
    second = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert not second["has_more"]
    assert second["pending"] == 7
    assert service.history_reads == 1


def test_ai_budget_and_success_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_MAX_AI_CALLS", "2")
    engine = _seed(5)
    service = FakeGmailService([_mail(str(i), i, "uncertain") for i in range(5)])
    runner = Mock()
    runner.run.return_value.content = '{"label":"none","confidence":1,"evidence":""}'
    first = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=runner)
    assert first["stats"]["ai_calls"] == 2
    assert first["has_more"]
    result = first
    for _ in range(3):
        result = run_gmail_sync(
            engine, _reporter(tmp_path), service=service, llm=runner
        )
        if not result["has_more"]:
            break
    assert not result["has_more"]
    assert runner.run.call_count == 5
    assert Counter(service._messages.gets).most_common(1)[0][1] == 1


def test_no_decision_classification_survives_unrelated_application_changes(tmp_path):
    engine = _seed()
    service = FakeGmailService([_mail("m1", decision="uncertain")])
    runner = Mock()
    runner.run.return_value.content = '{"label":"none","confidence":1,"evidence":""}'
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=runner)
    reads = len(service._messages.gets)
    with Session(engine) as session:
        session.add(
            Job(id=2, source="manual", company="Another employer", title="Engineer")
        )
        session.add(Application(id=2, job_id=2, status="submitted"))
        session.commit()
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=runner)
    assert result["stats"]["ai_calls"] == 0
    assert result["stats"]["classification_cache_hits"] == 1
    assert runner.run.call_count == 1
    assert len(service._messages.gets) == reads
    assert not result["has_more"]


@pytest.mark.parametrize("decision", ["rejection", "uncertain"])
def test_known_email_reappearing_in_history_reuses_all_completed_work(
    tmp_path, decision
):
    engine = _seed()
    message = _mail("m1", decision=decision)
    service = FakeGmailService([message])
    runner = Mock()
    runner.run.return_value.content = '{"label":"none","confidence":1,"evidence":""}'
    first = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=runner)
    reads, calls = len(service._messages.gets), runner.run.call_count
    _history(service, [message])
    second = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=runner)
    assert second["pending"] == first["pending"]
    assert second["stats"]["cached"] == 1
    assert second["stats"]["metadata_reads"] == 0
    assert second["stats"]["body_reads"] == 0
    assert second["stats"]["ai_calls"] == 0
    assert len(service._messages.gets) == reads
    assert runner.run.call_count == calls


def test_restored_spam_email_refreshes_cached_exclusion(tmp_path):
    engine = _seed()
    message = {**_mail("m1"), "labelIds": ["SPAM"]}
    service = FakeGmailService([message])
    first = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert first["pending"] == 0
    assert first["stats"]["body_reads"] == 0
    message["labelIds"] = ["INBOX"]
    service.history_id = "2"
    service.history_pages = [
        {
            "historyId": "2",
            "history": [
                {
                    "labelsRemoved": [{"message": {"id": "m1"}, "labelIds": ["SPAM"]}],
                }
            ],
        }
    ]
    restored = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert restored["pending"] == 1
    assert restored["stats"]["metadata_reads"] == 1
    assert restored["stats"]["body_reads"] == 1


def test_enabling_ai_reconsiders_rules_only_no_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_MAX_AI_CALLS", "0")
    engine = _seed()
    service = FakeGmailService([_mail("m1", decision="uncertain")])
    runner = Mock()
    runner.run.return_value.content = '{"label":"none","confidence":1,"evidence":""}'
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=runner)
    runner.run.assert_not_called()
    reads = len(service._messages.gets)
    monkeypatch.setenv("GMAIL_MAX_AI_CALLS", "2")
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=runner)
    assert result["stats"]["ai_calls"] == 1
    assert len(service._messages.gets) == reads


def test_history_pagination_continues_across_runs_before_advancing_cursor(
    tmp_path, monkeypatch
):
    engine = _seed()
    service = FakeGmailService([])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    monkeypatch.setenv("GMAIL_SYNC_MAX_PAGES", "1")
    _history(
        service,
        [_mail("old", decision="interview", date=1000), _mail("new", date=2000)],
    )
    service.history_pages = [
        {
            "historyId": "2",
            "nextPageToken": "1",
            "history": [{"messagesAdded": [{"message": {"id": "old"}}]}],
        },
        {
            "historyId": "2",
            "history": [{"messagesAdded": [{"message": {"id": "new"}}]}],
        },
    ]
    first = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert first["has_more"]
    with Session(engine) as session:
        assert (
            session.exec(select(GmailSyncState)).one().cursors["history"]["cursor"]
            == "1"
        )
    second = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert not second["has_more"]
    assert service.history_reads == 2
    with Session(engine) as session:
        assert (
            session.exec(select(GmailSyncState)).one().cursors["history"]["cursor"]
            == "2"
        )
        assert (
            session.exec(select(Notification).where(Notification.state == "pending"))
            .one()
            .proposed_status
            == "rejected"
        )


def test_expired_backfill_page_token_restarts_without_redownloading(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GMAIL_SYNC_MAX_PAGES", "1")
    monkeypatch.setenv("GMAIL_MAX_MESSAGES", "1")
    engine = _seed(2)
    service = FakeGmailService([_mail("m0"), _mail("m1", company=1)])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    original = service._messages.list
    expired = False

    def listing(**kwargs):
        nonlocal expired
        if kwargs.get("pageToken") and not expired:
            expired = True
            request = Mock()
            request.execute.side_effect = _error(400)
            return request
        return original(**kwargs)

    monkeypatch.setattr(service._messages, "list", listing)
    interrupted = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert any("page cursor expired" in warning for warning in interrupted["warnings"])
    result = interrupted
    for _ in range(5):
        result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
        if not result["has_more"]:
            break
    assert not result["has_more"]
    assert result["pending"] == 2
    assert set(Counter(service._messages.gets).values()) == {1}


def test_adding_application_reconsiders_cached_unmatched_mail_without_rereading(
    tmp_path,
):
    engine = _seed(0)
    service = FakeGmailService([_mail("m1")])
    assert (
        run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)[
            "pending"
        ]
        == 0
    )
    reads = len(service._messages.gets)
    with Session(engine) as session:
        session.add(
            Job(
                id=1,
                source="manual",
                company="Employer 0",
                title="Senior Engineer",
                url="https://employer0.com/jobs/R900000",
            )
        )
        session.add(Application(id=1, job_id=1, status="submitted"))
        session.commit()
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert result["pending"] == 1
    assert len(service._messages.gets) == reads


def test_mailbox_switch_does_not_reuse_another_accounts_result(tmp_path):
    engine = _seed()
    service = FakeGmailService([_mail("same-id", decision="interview")])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    service.mailbox = "another@example.com"
    service._messages._messages = [_mail("same-id")]
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert result["stats"]["metadata_reads"] == 1
    with Session(engine) as session:
        assert len(session.exec(select(GmailSyncState)).all()) == 2
        assert len(session.exec(select(GmailReceipt)).all()) == 2
        notices = session.exec(select(Notification)).all()
        assert {n.proposed_status for n in notices} == {"interview", "rejected"}
        assert len({n.message_id for n in notices}) == 2


def test_overlapping_sync_is_rejected_before_any_mailbox_work(tmp_path):
    engine = _seed()
    service = FakeGmailService([])
    with _sync_lock(engine):
        with pytest.raises(GmailApiError, match="already running"):
            run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert service.profile_reads == 0


def test_failed_message_read_keeps_page_for_retry(tmp_path, monkeypatch):
    engine = _seed()
    service = FakeGmailService([_mail("m1")])
    original = service._messages.get
    failure = Mock()
    failure.execute.side_effect = _error(503)
    monkeypatch.setattr(service._messages, "get", lambda **kwargs: failure)
    with pytest.raises(GmailApiError):
        run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    monkeypatch.setattr(service._messages, "get", original)
    assert (
        run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)[
            "pending"
        ]
        == 1
    )


def test_receipt_and_notification_roll_back_together(tmp_path, monkeypatch):
    from resume_tailor_harness.gmail.processing import MessageProcessor

    engine = _seed()
    service = FakeGmailService([_mail("m1")])
    original = MessageProcessor._propose_latest
    monkeypatch.setattr(
        MessageProcessor,
        "_propose_latest",
        Mock(side_effect=RuntimeError("write failed")),
    )
    with pytest.raises(RuntimeError, match="write failed"):
        run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    with Session(engine) as session:
        assert not session.exec(select(GmailReceipt)).all()
        assert not session.exec(select(Notification)).all()
        assert session.exec(select(GmailSyncState)).one().cursors["recruiting"][
            "pending"
        ] == ["m1"]
    monkeypatch.setattr(MessageProcessor, "_propose_latest", original)
    assert (
        run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)[
            "pending"
        ]
        == 1
    )


def test_file_lock_protects_separate_workers(tmp_path):
    from filelock import FileLock

    path = tmp_path / "workspace.db"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    with FileLock(str(path) + ".gmail-sync.lock"):
        with pytest.raises(GmailApiError, match="already running"):
            with _sync_lock(engine):
                pytest.fail("Acquired another worker's lock")


def test_unread_label_changes_do_not_trigger_message_reads(tmp_path):
    engine = _seed()
    service = FakeGmailService([_mail("m1")])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    service.history_id = "2"
    service.history_pages = [
        {
            "historyId": "2",
            "history": [
                {
                    "labelsRemoved": [
                        {"message": {"id": "m1"}, "labelIds": ["UNREAD"]}
                    ],
                    "messages": [{"id": "m1"}],
                }
            ],
        }
    ]
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert result["stats"]["metadata_reads"] == 0
    assert result["pending"] == 1


def test_archiving_an_application_cannot_transfer_its_email_to_another_role(tmp_path):
    from resume_tailor_harness.tracking.tables import utcnow

    engine = _seed()
    message = _mail("m1")
    message["snippet"] = "We have decided not to move forward with your application."
    message["payload"] = {
        "mimeType": "text/plain",
        "body": {
            "data": base64.urlsafe_b64encode(message["snippet"].encode()).decode()
        },
    }
    service = FakeGmailService([message])
    run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    with Session(engine) as session:
        old = session.get(Job, 1)
        assert old is not None
        old.archived_at = utcnow()
        session.add(old)
        session.add(
            Job(id=2, source="manual", company="Employer 0", title="Different Engineer")
        )
        session.add(Application(id=2, job_id=2, status="submitted"))
        session.commit()
    result = run_gmail_sync(engine, _reporter(tmp_path), service=service, llm=None)
    assert result["pending"] == 0
    assert result["stats"]["ambiguous"] == 1
