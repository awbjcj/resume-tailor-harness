"""Selection and handoff cross the same factual safety seam."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.tracking.tables import (
    Application,
    ApplicationEvent,
    CoverLetter,
    Job,
    ResumeVersion,
)


@pytest.fixture
def client_app(tmp_path):
    app = create_app(
        db_url="sqlite://", data_dir=tmp_path / "data", config_dir=tmp_path / "config"
    )
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            job = Job(
                source="manual", jd_text="Saved full description", status="approved"
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            assert job.id is not None
            job_id = job.id
        yield client, app, job_id


def save_rows(app, *rows):
    with Session(app.state.engine) as session:
        session.add_all(rows)
        session.commit()
        for row in rows:
            session.refresh(row)
        return [row.id for row in rows]


@pytest.mark.parametrize(
    "gate", ["provenance", "skill-naming", "numeric-evidence", "fact-check"]
)
def test_resume_selection_rejects_failed_gates_without_creating_application(
    client_app, gate
):
    client, app, job_id = client_app
    [version_id] = save_rows(
        app,
        ResumeVersion(
            job_id=job_id,
            fact_check_passed=True,
            critique_json=[{"reviewer": gate, "score": 0, "passed": False}],
        ),
    )
    response = client.post(f"/api/jobs/{job_id}/select-resume/{version_id}")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "MATERIAL_NOT_ELIGIBLE"
    with Session(app.state.engine) as session:
        assert not session.exec(select(Application)).all()
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["resumeVersions"][0]["applicationEligible"] is False
    assert (
        client.get(f"/api/jobs/{job_id}/application-context").json()["attachments"]
        == []
    )


def test_cover_letter_selection_rejects_failed_check_without_side_effects(client_app):
    client, app, job_id = client_app
    [letter_id] = save_rows(app, CoverLetter(job_id=job_id, fact_check_passed=False))
    response = client.post(f"/api/jobs/{job_id}/select-cover-letter/{letter_id}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MATERIAL_NOT_ELIGIBLE"
    with Session(app.state.engine) as session:
        assert not session.exec(select(Application)).all()


def test_copy_and_sdk_preserve_exact_older_selections_and_unavailable_pdf(
    client_app, tmp_path
):
    client, app, job_id = client_app
    older_id, newer_id, letter_id = save_rows(
        app,
        ResumeVersion(
            job_id=job_id,
            round=1,
            fact_check_passed=True,
            pdf_path=str(tmp_path / "gone.pdf"),
        ),
        ResumeVersion(job_id=job_id, round=2, fact_check_passed=True),
        CoverLetter(job_id=job_id, fact_check_passed=True),
    )
    first = client.post(f"/api/jobs/{job_id}/select-resume/{older_id}")
    assert first.status_code == 200
    second = client.post(f"/api/jobs/{job_id}/select-cover-letter/{letter_id}")
    assert second.status_code == 200
    assert second.json()["status"] == "ready" and second.json()["submittedAt"] is None
    copied = client.get(f"/api/jobs/{job_id}/application-prompt")
    context = client.get(f"/api/jobs/{job_id}/application-context")
    assert copied.status_code == context.status_code == 200
    materials = copied.json()["materials"]
    assert materials == context.json()["materials"]
    assert materials["selectedResumeVersionId"] == older_id
    assert materials["selectedCoverLetterId"] == letter_id
    selected = [item for item in materials["items"] if item["isSelected"]]
    assert {(item["kind"], item["id"]) for item in selected} == {
        ("resume", older_id),
        ("cover_letter", letter_id),
    }
    assert all(
        item["applicationEligible"]
        and not item["pdfAvailable"]
        and item["downloadPath"] is None
        for item in selected
    )
    for response in (copied, context):
        prompt = response.json()["prompt"]
        assert (
            f"Resume #{older_id}: selected for application; PDF unavailable" in prompt
        )
        assert f"Resume #{newer_id}: available alternative; not selected" in prompt
        assert "This prompt does not attach any files" in prompt
        assert "can authenticate to Resume Harness" in prompt
        assert "Stop before final submission" in prompt
        assert str(tmp_path) not in response.text
    assert "Resume Harness app: http://testserver" in copied.json()["prompt"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["resumeVersions"][0]["pdfAvailable"] is False
    with Session(app.state.engine) as session:
        application = session.exec(select(Application)).one()
        assert (
            application.resume_version_id == older_id
            and application.cover_letter_id == letter_id
        )
        assert not session.exec(select(ApplicationEvent)).all()


def test_legacy_unsafe_and_missing_selected_materials_remain_explicit(
    client_app, tmp_path
):
    client, app, job_id = client_app
    pdf = tmp_path / "unsafe.pdf"
    pdf.write_bytes(b"%PDF")
    [unsafe_id] = save_rows(
        app, ResumeVersion(job_id=job_id, pdf_path=str(pdf), fact_check_passed=False)
    )
    save_rows(
        app,
        Application(job_id=job_id, resume_version_id=unsafe_id, cover_letter_id=999),
    )
    for route in ("application-prompt", "application-context"):
        response = client.get(f"/api/jobs/{job_id}/{route}")
        assert response.status_code == 200
        body = response.json()
        assert body["materials"]["selectedResumeVersionId"] == unsafe_id
        assert body["materials"]["selectedCoverLetterId"] == 999
        assert {item["blockReason"] for item in body["materials"]["items"]} == {
            "fact_lock_failed",
            "material_missing",
        }
        assert all(
            not item["applicationEligible"] and item["downloadPath"] is None
            for item in body["materials"]["items"]
        )
        assert "BLOCKED: factual safety check failed; do not upload" in body["prompt"]
        assert "BLOCKED: document is missing; do not upload" in body["prompt"]
        assert str(pdf) not in response.text
        if route == "application-context":
            assert body["attachments"] == []
    assert client.delete(f"/api/jobs/{job_id}/select-resume").status_code == 200
    assert client.delete(f"/api/jobs/{job_id}/select-cover-letter").status_code == 200


@pytest.mark.parametrize("submitted", [False, True])
def test_basic_copy_remains_available_for_raw_or_submitted_job(client_app, submitted):
    client, app, job_id = client_app
    with Session(app.state.engine) as session:
        job = session.get(Job, job_id)
        assert job is not None
        if submitted:
            session.add(Application(job_id=job_id, status="submitted"))
        else:
            job.status = "raw"
            session.add(job)
        session.commit()
    copied = client.get(f"/api/jobs/{job_id}/application-prompt")
    assert copied.status_code == 200
    assert copied.headers["cache-control"] == "no-store"
    assert client.get(f"/api/jobs/{job_id}/application-context").status_code == 409
    with Session(app.state.engine) as session:
        applications = session.exec(select(Application)).all()
        assert len(applications) == (1 if submitted else 0)


def test_copy_and_sdk_use_only_questions_scoped_to_this_job(client_app):
    client, app, job_id = client_app
    [other_job] = save_rows(
        app, Job(source="manual", jd_text="Other role", status="approved")
    )
    for scope, target, wording in (
        ("profile", None, "Personal question"),
        ("job", job_id, "This role question"),
        ("job", other_job, "Other role private question"),
    ):
        response = client.post(
            "/api/application-questions",
            json={"scope": scope, "jobId": target, "question": wording},
        )
        assert response.status_code == 200
    for route in ("application-prompt", "application-context"):
        prompt = client.get(f"/api/jobs/{job_id}/{route}").json()["prompt"]
        assert "Personal question" in prompt and "This role question" in prompt
        assert "Other role private question" not in prompt
