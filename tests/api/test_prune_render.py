from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.routers import resumes
from resume_tailor_harness.db import get_session
from resume_tailor_harness.models.profile import Contact
from resume_tailor_harness.models.resume import ResumeContent
from resume_tailor_harness.render.render_config import RenderConfig
from resume_tailor_harness.render.renderer import PageFitError
from resume_tailor_harness.services import rendering
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

    def fake_render(session, version_id, *, template_id=None):
        from resume_tailor_harness.tracking.repository import get_resume_version

        assert template_id is None
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


def test_style_override_replaces_only_the_selected_versions_pdf(monkeypatch, tmp_path):
    config = RenderConfig(template="classic", output_dir=str(tmp_path / "output"))
    monkeypatch.setattr(rendering, "_load_config", lambda _: config)
    app = create_app(db_url="sqlite://", data_dir=tmp_path / "data", config_dir=tmp_path / "config")
    with TestClient(app) as client:
        with get_session(app.state.engine) as session:
            job = Job(source="manual", company="Acme", title="Engineer")
            session.add(job)
            session.flush()
            assert job.id is not None
            content = ResumeContent(contact=Contact(name="Ada Lovelace")).model_dump(mode="json")
            version = ResumeVersion(job_id=job.id, round=1, fact_check_passed=True, content_json=content)
            other = ResumeVersion(job_id=job.id, round=1, fact_check_passed=True, content_json=content)
            session.add_all([version, other])
            session.flush()
            job_id, version_id, other_id = job.id, version.id, other.id
            session.commit()

        url = f"/api/resume-versions/{version_id}"
        initial = client.post(f"{url}/render")
        assert initial.status_code == 200
        assert initial.json()["pdfTemplateId"] == "classic"
        original_pdf = client.get(f"{url}/pdf").content
        assert original_pdf.startswith(b"%PDF")
        assert client.post(f"/api/jobs/{job_id}/select-resume/{version_id}").status_code == 200

        replacement = client.post(f"{url}/render", json={"templateId": "modern"})
        assert replacement.status_code == 200
        assert replacement.json()["pdfTemplateId"] == "modern"
        assert replacement.json()["pdfPath"] == initial.json()["pdfPath"]
        replacement_pdf = client.get(f"{url}/preview").content
        assert replacement_pdf.startswith(b"%PDF") and replacement_pdf != original_pdf
        assert client.get(f"{url}/pdf").content == replacement_pdf

        invalid = client.post(f"{url}/render", json={"templateId": "custom:../unsafe"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "template_not_found"
        assert client.get(f"{url}/pdf").content == replacement_pdf
        detail = client.get(f"/api/jobs/{job_id}").json()
        assert detail["application"]["resumeVersionId"] == version_id
        versions = {row["id"]: row for row in detail["resumeVersions"]}
        assert versions[version_id]["pdfTemplateId"] == "modern"
        assert versions[other_id]["pdfAvailable"] is False
        assert client.get(f"{url}/content").json() == content
        assert config.template == "classic"
