from typing import Any

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine

from resume_tailor_harness.discovery.connectors.base import RawJob
from resume_tailor_harness.services import redo
from resume_tailor_harness.tracking.dedup import compute_dedup_key
from resume_tailor_harness.tracking.repository import save_job
from resume_tailor_harness.tracking.tables import Job, JobStatus


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as database:
        yield database


def _tailored_job(session, **overrides) -> Job:
    values: dict[str, Any] = {
        "source": "greenhouse",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "company": "Acme",
        "title": "Staff Engineer",
        "jd_text": "old text",
        "status": JobStatus.tailored.value,
    }
    values.update(overrides)
    return save_job(session, Job(**values))


def test_repull_replaces_frozen_jd_text_on_a_tailored_job(session, monkeypatch):
    """The motivating case: merge.decide() freezes jd_text past raw; redo does not."""
    job = _tailored_job(session)
    monkeypatch.setattr(
        redo,
        "job_from_url",
        lambda url, agent, allow_browser, **kwargs: RawJob(
            source="url",
            url=url,
            company="Acme",
            title="Staff Engineer",
            location="Remote",
            jd_text="fresh text",
        ),
    )

    outcome, failure = redo.repull_job(
        session, job, agent=object(), allow_browser=False
    )

    assert outcome.status == "ok"
    assert failure is None
    assert job.jd_text == "fresh text"
    assert job.location == "Remote"
    assert job.status == JobStatus.tailored.value  # never regressed
    assert job.source == "greenhouse"  # provenance preserved


def test_repull_skips_a_job_with_no_url(session):
    job = _tailored_job(session, url=None, source="manual")

    outcome, failure = redo.repull_job(
        session, job, agent=object(), allow_browser=False
    )

    assert outcome.status == "skipped"
    assert outcome.detail == "no source URL"
    assert failure is None
    assert job.jd_text == "old text"


def test_recovery_review_preserves_saved_job_and_status(session, monkeypatch):
    from resume_tailor_harness.discovery.url_ingest.recovery import RecoveryRequired

    job = _tailored_job(
        session, url="https://www.indeed.com/viewjob?jk=1", location="Remote"
    )

    def unresolved(url, **kwargs):
        assert kwargs["recovery_hints"].company == "Acme"
        raise RecoveryRequired(
            "Multiple matching roles", ("https://jobs.lever.co/acme/1",)
        )

    monkeypatch.setattr(redo, "job_from_url", unresolved)
    outcome, failure = redo.repull_job(
        session, job, agent=object(), allow_browser=False
    )
    assert outcome.status == "failed" and failure is not None
    assert "https://jobs.lever.co/acme/1" in outcome.detail
    session.refresh(job)
    assert job.url == "https://www.indeed.com/viewjob?jk=1"
    assert job.jd_text == "old text" and job.status == JobStatus.tailored.value


def test_recovery_updates_apply_url_in_place(session, monkeypatch):
    job = _tailored_job(session, url="https://www.indeed.com/viewjob?jk=1")
    identifier = job.id
    monkeypatch.setattr(
        redo,
        "job_from_url",
        lambda *args, **kwargs: RawJob(
            source="url",
            url="https://jobs.lever.co/acme/1",
            company="Acme",
            title="Staff Engineer",
            location="Remote",
            jd_text="Recovered full description",
        ),
    )
    outcome, failure = redo.repull_job(
        session, job, agent=object(), allow_browser=False
    )
    session.refresh(job)
    assert job.id == identifier and job.status == JobStatus.tailored.value
    assert job.url == "https://jobs.lever.co/acme/1"
    assert outcome.status == "ok" and "indeed.com" in outcome.detail
    assert failure is None


def test_repull_failure_preserves_jd_text(session, monkeypatch):
    job = _tailored_job(session)

    def _boom(url, agent, allow_browser, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(redo, "job_from_url", _boom)

    outcome, failure = redo.repull_job(
        session, job, agent=object(), allow_browser=False
    )

    assert outcome.status == "failed"
    assert job.jd_text == "old text"
    assert failure is not None
    assert failure.error_type == "ConnectError"


def test_repull_reports_failure_when_no_description_extracted(session, monkeypatch):
    job = _tailored_job(session)
    monkeypatch.setattr(
        redo, "job_from_url", lambda url, agent, allow_browser, **kwargs: None
    )

    outcome, _failure = redo.repull_job(
        session, job, agent=object(), allow_browser=False
    )

    assert outcome.status == "failed"
    assert outcome.detail == "no job description found"
    assert job.jd_text == "old text"


def test_repull_recomputes_dedup_key_when_title_changes(session, monkeypatch):
    job = _tailored_job(session)
    original_key = job.dedup_key
    monkeypatch.setattr(
        redo,
        "job_from_url",
        lambda url, agent, allow_browser, **kwargs: RawJob(
            source="url",
            url=url,
            company="Acme",
            title="Principal Engineer",
            location=None,
            jd_text="fresh text",
        ),
    )

    redo.repull_job(session, job, agent=object(), allow_browser=False)

    assert job.title == "Principal Engineer"
    assert job.dedup_key != original_key


def test_repull_keeps_identity_when_the_new_key_would_collide(session, monkeypatch):
    job = _tailored_job(session)
    original_key = job.dedup_key
    colliding_key = compute_dedup_key("Acme", "Principal Engineer")
    _tailored_job(
        session,
        company="Acme",
        title="Principal Engineer",
        dedup_key=colliding_key,
        url="https://boards.greenhouse.io/acme/jobs/2",
    )
    monkeypatch.setattr(
        redo,
        "job_from_url",
        lambda url, agent, allow_browser, **kwargs: RawJob(
            source="url",
            url=url,
            company="Acme",
            title="Principal Engineer",
            location=None,
            jd_text="fresh text",
        ),
    )

    outcome, _ = redo.repull_job(session, job, agent=object(), allow_browser=False)

    assert outcome.status == "ok"
    assert job.jd_text == "fresh text"  # text still taken
    assert job.title == "Staff Engineer"  # identity untouched
    assert job.dedup_key == original_key
