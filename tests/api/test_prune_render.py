from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.routers import resumes
from resume_tailor_harness.render.renderer import PageFitError
from resume_tailor_harness.db import get_session
from resume_tailor_harness.tracking.tables import Job, JobStatus, ResumeVersion


def _client():
    return TestClient(create_app(db_url="sqlite://"))


def test_prune_dry_run_reports_counts():
    client = _client()
    with client:
        with get_session(client.app.state.engine) as s:  # type: ignore[union-attr]
            s.add(Job(source="manual", jd_text="x", status=JobStatus.rejected.value))
            s.commit()
        body = client.post("/api/prune", json={"dryRun": True}).json()
    assert body["rejected"] >= 1
    assert "archived" in body


def test_render_endpoint_invokes_service(monkeypatch, tmp_path):
    client = _client()
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def fake_render(session, version_id, *, render_path="config/render.yaml"):
        from resume_tailor_harness.tracking.repository import get_resume_version

        v = get_resume_version(session, version_id)
        assert v is not None
        v.pdf_path = str(pdf)
        session.add(v)
        session.commit()
        return pdf

    monkeypatch.setattr(resumes, "render_resume_version", fake_render)
    with client:
        with get_session(client.app.state.engine) as s:  # type: ignore[union-attr]
            job = Job(source="manual", jd_text="x")
            s.add(job)
            s.commit()
            s.refresh(job)
            assert job.id is not None
            v = ResumeVersion(job_id=job.id, round=0)
            s.add(v)
            s.commit()
            s.refresh(v)
            vid = v.id
        body = client.post(f"/api/resume-versions/{vid}/render").json()
    assert body["pdfPath"].endswith("r.pdf")


def test_render_overflow_is_an_actionable_422(monkeypatch):
    def cannot_fit(*args, **kwargs):
        raise PageFitError(2, 1)

    monkeypatch.setattr(resumes, "render_resume_version", cannot_fit)
    with _client() as client:
        response = client.post("/api/resume-versions/1/render")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "resume_page_overflow"
    assert "two-page" in response.json()["error"]["message"]
