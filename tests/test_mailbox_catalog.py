"""Page freshness and bounded reads through the shared processing interface."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlmodel import Session, select

from resume_tailor_harness.gmail.classify import SyncClassifier
from resume_tailor_harness.gmail.client import email_from_payload
from resume_tailor_harness.gmail.processing import MessageProcessor
from resume_tailor_harness.gmail.tables import GmailReceipt
from resume_tailor_harness.tracking.tables import Application, Job, Notification
from scripts.perf_harness import count_queries
from tests.test_gmail_incremental_sync import _mail, _seed


def processor(session, account="mailbox-fixture"):
    return MessageProcessor(
        None,
        session,
        account,
        SyncClassifier(None, None, 0, lambda _: None),
        lambda: None,
        source="mailbox",
    )


@pytest.mark.parametrize("count", [1, 10, 100])
def test_fresh_page_after_commit_has_bounded_narrow_reads(count):
    engine = _seed(count)
    try:
        with Session(engine) as session:
            reader = processor(session)
            session.commit()
            emails = [
                email_from_payload(str(i), _mail(str(i), company=i), recruiting=True)
                for i in range(count)
            ]
            with count_queries(engine, record_sql=True) as queries:
                reader.process_emails(emails)
            assert (
                queries.reads == 5
            )  # catalog, receipts, stale decisions, latest, notices
            catalog_sql = next(sql for sql in queries.statements if "JOIN jobs" in sql)
            assert all(
                column not in catalog_sql
                for column in (
                    "jd_text",
                    "criteria_json",
                    "analysis_meta_json",
                    "fit_rationale",
                    "notes",
                )
            )
            assert reader.stats["matched"] == count
            assert len(session.exec(select(Notification)).all()) == count
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "edit", ["archive", "closed", "submitted", "competing", "metadata", "delete"]
)
def test_next_page_observes_edits_from_another_session(edit):
    engine = _seed()
    try:
        with Session(engine) as session:
            reader = processor(session)
            session.commit()
            with Session(engine) as writer:
                job = writer.get(Job, 1)
                app = writer.get(Application, 1)
                assert job is not None and app is not None
                if edit == "archive":
                    job.archived_at = datetime.now(timezone.utc)
                elif edit == "closed":
                    app.status = "closed"
                elif edit == "submitted":
                    app.submitted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
                elif edit == "competing":
                    writer.add(
                        Job(
                            id=2,
                            source="manual",
                            company=job.company,
                            title=job.title,
                            url=job.url,
                        )
                    )
                    writer.add(Application(id=2, job_id=2, status="submitted"))
                elif edit == "metadata":
                    job.url = "https://other.example/jobs/R123456"
                    job.source_identity = "R123456"
                elif edit == "delete":
                    writer.delete(app)
                writer.add(job)
                if edit != "delete":
                    writer.add(app)
                writer.commit()
            reader.process_emails(
                [email_from_payload("new", _mail("new"), recruiting=True)]
            )
            assert session.exec(select(Notification)).all() == []
    finally:
        engine.dispose()


def test_restore_and_new_applications_are_visible_without_recreating_processor():
    engine = _seed()
    try:
        with Session(engine) as session:
            job = session.get(Job, 1)
            assert job is not None
            job.archived_at = datetime.now(timezone.utc)
            session.commit()
            reader = processor(session)
            session.commit()
            with Session(engine) as writer:
                restored = writer.get(Job, 1)
                assert restored is not None
                restored.archived_at = None
                writer.add(restored)
                writer.add(
                    Job(
                        id=2,
                        source="manual",
                        company="Employer 1",
                        title="Senior Engineer",
                        url="https://employer1.com/jobs/R900001",
                    )
                )
                writer.add(Application(id=2, job_id=2, status="submitted"))
                writer.commit()
            reader.process_emails(
                [
                    email_from_payload(
                        str(i), _mail(str(i), company=i), recruiting=True
                    )
                    for i in range(2)
                ]
            )
            assert {
                notice.application_id
                for notice in session.exec(select(Notification)).all()
            } == {1, 2}
    finally:
        engine.dispose()


def test_page_refresh_keeps_classification_reuse_on_catalog_change():
    engine = _seed()
    try:
        with Session(engine) as session:
            reader = processor(session)
            email = email_from_payload("cached", _mail("cached"), recruiting=True)
            reader.process_emails([email])
            session.commit()
            old_classifier = reader.classifier.classify
            reader.classifier.classify = lambda email: pytest.fail(
                "Completed classification must be reused"
            )
            job = session.get(Job, 1)
            assert job is not None
            job.title = "Senior Software Engineer"
            session.commit()
            reader.process_emails([email])
            assert reader.stats["classification_cache_hits"] == 1
            assert reader.stats["cached"] == 1
            assert session.exec(select(GmailReceipt)).one().label == "rejection"
            reader.classifier.classify = old_classifier
    finally:
        engine.dispose()


@pytest.mark.parametrize("other_account", [False, True])
@pytest.mark.parametrize("restore_latest", [False, True])
def test_catalog_edits_reconcile_cached_decisions_before_chronology(
    other_account, restore_latest
):
    engine = _seed(2)
    try:
        with Session(engine) as session:
            if restore_latest:
                app = session.get(Application, 1)
                assert app is not None
                app.status = "closed"
                session.commit()
            reader = processor(session)
            reader.process_emails(
                [
                    email_from_payload(
                        "first",
                        _mail(
                            "first",
                            decision="rejection" if restore_latest else "interview",
                            date=2000 if restore_latest else 1000,
                        ),
                        recruiting=True,
                    )
                ]
            )
            session.commit()
            with Session(engine) as writer:
                job = writer.get(Job, 2)
                app = writer.get(Application, 1)
                assert job is not None and app is not None
                job.title = "Edited unrelated role"
                app.status = "submitted"
                writer.add(job)
                writer.add(app)
                writer.commit()
            if other_account:
                reader = processor(session, "mailbox-other")
            classify = Mock(wraps=reader.classifier.classify)
            reader.classifier.classify = classify
            reader.process_emails(
                [
                    email_from_payload(
                        "second",
                        _mail(
                            "second",
                            decision="interview" if restore_latest else "rejection",
                            date=1000 if restore_latest else 2000,
                        ),
                        recruiting=True,
                    )
                ]
            )
            notices = session.exec(select(Notification)).all()
            pending = [notice for notice in notices if notice.state == "pending"]
            assert [
                (notice.application_id, notice.proposed_status) for notice in pending
            ] == [(1, "rejected")]
            assert pending[0].message_id.endswith(
                ":first" if restore_latest else ":second"
            )
            if not restore_latest:
                assert (
                    next(
                        notice
                        for notice in notices
                        if notice.message_id.endswith(":first")
                    ).state
                    == "superseded"
                )
            assert (
                classify.call_count == 1
            )  # the existing decision reuses its classification
            assert reader.stats["cached"] == 1
            assert (
                session.exec(
                    select(GmailReceipt).where(GmailReceipt.message_id == "first")
                )
                .one()
                .bound_application_id
                == 1
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("count", [1, 501])
def test_revalidation_batches_keep_equal_timestamp_order_and_cached_classifications(
    count,
):
    engine = _seed(2)
    try:
        with Session(engine) as session:
            reader = processor(session)
            reader.process_emails(
                [
                    email_from_payload(
                        str(index),
                        _mail(str(index), decision="interview", date=1000),
                        recruiting=True,
                    )
                    for index in range(count)
                ]
            )
            session.commit()
            job = session.get(Job, 2)
            assert job is not None
            job.title = "Edited unrelated role"
            session.commit()
            classify = Mock(wraps=reader.classifier.classify)
            reader.classifier.classify = classify
            reader.process_emails(
                [email_from_payload("new", _mail("new", date=1000), recruiting=True)]
            )
            pending = session.exec(
                select(Notification).where(Notification.state == "pending")
            ).all()
            assert [
                (notice.proposed_status, notice.message_id) for notice in pending
            ] == [("rejected", "mailbox:mailbox-fixture:new")]
            assert reader.stats["classification_cache_hits"] == count
            assert classify.call_count == 1
    finally:
        engine.dispose()
