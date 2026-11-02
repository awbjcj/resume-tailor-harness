"""The dashboard and Job screen agree about work, even when status is historical."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.tracking.tables import (
    Application,
    ApplicationEvent,
    Job,
    ResumeVersion,
)


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(
        db_url="sqlite://",
        config_dir=tmp_path / "config",
        env_path=tmp_path / ".env",
        data_dir=tmp_path / "data",
    )
    with TestClient(app) as client:
        yield app, client


def test_next_steps_agree_with_queue_membership_and_preserve_selection(
    app_client, tmp_path
):
    app, client = app_client
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-test")
    expected = {}
    with Session(app.state.engine) as session:
        for stage, expected_kind, passed, path in [
            ("raw", "triage", None, None),
            ("shortlisted", "approve", None, None),
            ("approved", "tailor", None, None),
            ("tailored", "review", False, None),
            ("tailored", "render", True, None),
            ("rendered", "apply", True, str(pdf)),
            ("rendered", "render", True, str(tmp_path / "gone.pdf")),
        ]:
            job = Job(
                source="manual", status=stage, company="Example", title=expected_kind
            )
            session.add(job)
            session.flush()
            assert job.id is not None
            if passed is not None:
                session.add(
                    ResumeVersion(
                        job_id=job.id,
                        round=1,
                        content_json={},
                        fact_check_passed=passed,
                        pdf_path=path,
                    )
                )
            expected[job.id] = expected_kind
        # The user's older choice must not silently become the newest document.
        job = Job(
            source="manual", status="rendered", company="Example", title="Older choice"
        )
        session.add(job)
        session.flush()
        assert job.id is not None
        older = ResumeVersion(
            job_id=job.id, round=1, content_json={}, fact_check_passed=True
        )
        session.add(older)
        session.flush()
        session.add(
            ResumeVersion(
                job_id=job.id,
                round=2,
                content_json={},
                fact_check_passed=True,
                pdf_path=str(pdf),
            )
        )
        session.add(Application(job_id=job.id, resume_version_id=older.id))
        expected[job.id] = "render"
        session.commit()

    summary = client.get("/api/dashboard/summary").json()
    assert summary["queues"] == {
        "triage": 1,
        "approve": 1,
        "tailor": 1,
        "review": 1,
        "render": 3,
        "apply": 1,
    }
    for job_id, kind in expected.items():
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        step = response.json()["nextStep"]
        assert step["kind"] == kind
        assert f"job={job_id}" in step["href"]
        if kind in {"render", "review", "apply"}:
            assert "tab=resumes" in step["href"]
    assert set(summary["queueTargets"]) == {
        "triage",
        "approve",
        "tailor",
        "review",
        "render",
        "apply",
    }


@pytest.mark.parametrize("history", ["status", "timestamp", "event"])
def test_submission_is_not_pending_apply_even_after_manual_reset(
    app_client, tmp_path, history
):
    app, client = app_client
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-test")
    with Session(app.state.engine) as session:
        job = Job(source="manual", status="rendered", company="Example")
        session.add(job)
        session.flush()
        assert job.id is not None
        job_id = job.id
        session.add(
            ResumeVersion(
                job_id=job_id,
                round=1,
                content_json={},
                fact_check_passed=True,
                pdf_path=str(pdf),
            )
        )
        application = Application(
            job_id=job_id,
            status="submitted" if history == "status" else "ready",
            submitted_at=datetime.now(timezone.utc) if history == "timestamp" else None,
        )
        session.add(application)
        session.flush()
        assert application.id is not None
        if history == "event":
            session.add(
                ApplicationEvent(
                    application_id=application.id,
                    kind="application_submitted",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        session.commit()
    summary = client.get("/api/dashboard/summary").json()
    assert not any(summary["queues"].values())
    assert summary["applied"] == 1
    step = client.get(f"/api/jobs/{job_id}").json()["nextStep"]
    assert step["kind"] == "track"
    assert "tab=tracking" in step["href"]


def test_failed_selected_resume_is_reviewed_instead_of_replaced(app_client, tmp_path):
    app, client = app_client
    pdf = tmp_path / "safe.pdf"
    pdf.write_bytes(b"%PDF-test")
    with Session(app.state.engine) as session:
        job = Job(source="manual", status="rendered")
        session.add(job)
        session.flush()
        assert job.id is not None
        job_id = job.id
        old = ResumeVersion(
            job_id=job_id, round=1, content_json={}, fact_check_passed=False
        )
        session.add(old)
        session.flush()
        session.add(
            ResumeVersion(
                job_id=job_id,
                round=2,
                content_json={},
                fact_check_passed=True,
                pdf_path=str(pdf),
            )
        )
        session.add(Application(job_id=job_id, resume_version_id=old.id))
        session.commit()
        selected_id = old.id
    step = client.get(f"/api/jobs/{job_id}").json()["nextStep"]
    assert step["kind"] == "review"
    assert step["resumeVersionId"] == selected_id
