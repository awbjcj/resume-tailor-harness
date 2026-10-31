import httpx
from sqlalchemy.orm import Session as SystemSession
from sqlmodel import Session

from resume_harness_sdk import ResumeHarness
from resume_tailor_harness.models.profile import Contact, ProfileFacts
from resume_tailor_harness.models.review import ReviewCritique
from resume_tailor_harness.profile.store import save_facts
from resume_tailor_harness.services import external_tailoring as service
from resume_tailor_harness.tenancy.secrets import hash_secret
from resume_tailor_harness.tenancy.system_db import ApiToken, User
from resume_tailor_harness.tracking.tables import Job, ResumeVersion


def seed(mu_app, mu_client):
    assert (
        mu_client.post(
            "/api/auth/login",
            json={"identifier": "owner", "password": "owner-password"},
        ).status_code
        == 200
    )
    token = mu_client.post("/api/account/tokens", json={"name": "SDK test"}).json()
    mu_client.cookies.clear()
    facts = ProfileFacts(contact=Contact(name="Applicant"))
    save_facts(facts, mu_app.state.default_context.paths.profile_dir / "facts.json")
    with Session(mu_app.state.engine) as session:
        job = Job(
            source="manual", jd_text="Test job", company="Example", title="Engineer"
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.id is not None
        return token, job.id, facts


def test_sdk_against_real_api_with_pat_review_and_revocation(
    mu_app, mu_client, monkeypatch
):
    token, job_id, facts = seed(mu_app, mu_client)
    monkeypatch.setattr(service, "build_reviewers", lambda *a, **kw: {})

    def panel(content, facts, jd, config, reviewers, *, render_config=None):
        assert render_config is not None
        return [
            ReviewCritique(reviewer=r.name, score=100, passed=True)
            for r in config.reviewers
        ]

    monkeypatch.setattr(service, "run_panel", panel)

    def transport(request):
        response = mu_client.request(
            request.method,
            str(request.url),
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(
            response.status_code, headers=response.headers, content=response.content
        )

    with ResumeHarness(
        base_url="https://testserver",
        api_key=token["token"],
        transport=httpx.MockTransport(transport),
    ) as sdk:
        context = sdk.authoring_context(job_id)
        assert context["profile"]["contact"]["name"] == "Applicant"
        content = {"contact": facts.contact.model_dump(mode="json")}
        assert sdk.validate_resume(
            job_id, content, context_revision=context["contextRevision"]
        )["valid"]
        run = sdk.submit_resume(
            job_id, content, context_revision=context["contextRevision"], agent="codex"
        )
        completed = sdk.wait(run, timeout=10, poll_interval=0.01)
        assert completed["result"]["passed"]
        version_id = completed["result"]["versionId"]
        assert sdk.get_resume(version_id)["contact"]["name"] == "Applicant"
        mu_client.delete(
            f"/api/account/tokens/{token['id']}",
            headers={"Authorization": f"Bearer {token['token']}"},
        )
        assert (
            mu_client.get(
                f"/api/jobs/{job_id}/authoring-context",
                headers={"Authorization": f"Bearer {token['token']}"},
            ).status_code
            == 401
        )


def test_another_tenant_cannot_read_authoring_context_or_content(mu_app, mu_client):
    _, job_id, facts = seed(mu_app, mu_client)
    with Session(mu_app.state.engine) as session:
        version = ResumeVersion(
            job_id=job_id, content_json={"contact": facts.contact.model_dump()}
        )
        session.add(version)
        session.commit()
        session.refresh(version)
        version_id = version.id
    with SystemSession(mu_app.state.system_engine) as session:
        session.add(
            User(id="other", username="other", password_hash="unused", role="user")
        )
        session.add(
            ApiToken(
                id="other-token",
                user_id="other",
                name="other",
                token_hash=hash_secret("rat_other"),
            )
        )
        session.commit()
    headers = {"Authorization": "Bearer rat_other"}
    assert (
        mu_client.get(
            f"/api/jobs/{job_id}/authoring-context", headers=headers
        ).status_code
        == 404
    )
    assert (
        mu_client.get(
            f"/api/resume-versions/{version_id}/content", headers=headers
        ).status_code
        == 404
    )


def test_missing_auth_profile_and_stale_request(mu_app, mu_client):
    token, job_id, facts = seed(mu_app, mu_client)
    url = f"/api/jobs/{job_id}/authoring-context"
    assert mu_client.get(url).status_code == 401
    headers = {"Authorization": f"Bearer {token['token']}"}
    revision = mu_client.get(url, headers=headers).json()["contextRevision"]
    path = mu_app.state.default_context.paths.profile_dir / "facts.json"
    save_facts(facts.model_copy(update={"summary": "Changed"}), path)
    response = mu_client.post(
        f"/api/jobs/{job_id}/external-resume",
        headers=headers,
        json={
            "content": {"contact": facts.contact.model_dump()},
            "contextRevision": revision,
        },
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "CONTEXT_STALE"
    )
    path.unlink()
    assert (
        mu_client.get(url, headers=headers).json()["error"]["code"]
        == "PROFILE_REQUIRED"
    )
