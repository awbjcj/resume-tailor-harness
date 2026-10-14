"""History selectors return scalars without materializing resume JSON."""

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from resume_tailor_harness.services.redo import _render_target
from resume_tailor_harness.tracking.repository import (
    latest_resume_version_id,
    next_resume_attempt,
)
from resume_tailor_harness.tracking.tables import Application, Job, ResumeVersion


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Job(id=1, source="test"), Job(id=2, source="test")])
        session.commit()
        yield session
    engine.dispose()


def test_empty_history_starts_at_one(session):
    assert next_resume_attempt(session, 1) == 1
    assert latest_resume_version_id(session, 1) is None


def test_attempt_and_latest_id_have_distinct_job_scoped_ordering(session):
    session.add_all(
        [
            ResumeVersion(id=1, job_id=1, attempt=0),  # legacy version
            ResumeVersion(id=2, job_id=1, attempt=8, round=2),
            ResumeVersion(id=3, job_id=1, attempt=8, round=1),
            ResumeVersion(id=4, job_id=1, attempt=3),
            ResumeVersion(id=5, job_id=2, attempt=99),
        ]
    )
    session.commit()

    assert next_resume_attempt(session, 1) == 9
    assert latest_resume_version_id(session, 1) == 4
    assert next_resume_attempt(session, 2) == 100
    assert latest_resume_version_id(session, 2) == 5
    assert next_resume_attempt(session, 3) == 1
    assert latest_resume_version_id(session, 3) is None


def test_selectors_see_pending_changes_without_committing(session):
    pending = ResumeVersion(job_id=1, attempt=0)
    session.add(pending)
    assert next_resume_attempt(session, 1) == 1
    assert latest_resume_version_id(session, 1) == pending.id

    pending.attempt = 12
    assert next_resume_attempt(session, 1) == 13
    session.rollback()
    assert latest_resume_version_id(session, 1) is None


@pytest.mark.parametrize(
    "selector", [next_resume_attempt, latest_resume_version_id, _render_target]
)
def test_history_reads_never_materialize_resume_versions(session, selector):
    session.add_all(
        ResumeVersion(
            job_id=1,
            attempt=i,
            content_json={"text": "x" * 8192},
            critique_json=[{"message": "x" * 1024}],
        )
        for i in range(100)
    )
    session.commit()
    session.expunge_all()
    loaded_versions = []

    def record_load(session, instance):
        if isinstance(instance, ResumeVersion):
            loaded_versions.append(instance)

    event.listen(session, "loaded_as_persistent", record_load)
    assert selector(session, 1) == 100
    assert loaded_versions == []


def test_render_prefers_application_selection_over_latest_version(session):
    session.add_all(
        [
            ResumeVersion(id=1, job_id=1),
            ResumeVersion(id=2, job_id=1),
            Application(job_id=1, resume_version_id=1),
        ]
    )
    session.commit()
    assert _render_target(session, 1) == 1


def test_render_falls_back_when_application_has_no_selection(session):
    session.add_all([ResumeVersion(id=1, job_id=1), Application(job_id=1)])
    session.commit()
    assert _render_target(session, 1) == 1
