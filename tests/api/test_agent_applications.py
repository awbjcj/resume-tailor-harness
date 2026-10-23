from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as SystemSession
from sqlmodel import Session, select

from resume_harness_sdk import APIError, ResumeHarness
from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.auth import hash_password
from resume_tailor_harness.api.schemas.agent_applications import (
    ApplicationProfilePatch,
    ApplicationProfileUpdate,
)
from resume_tailor_harness.db import init_db
from resume_tailor_harness.models.profile import Contact, ProfileFacts, Skill
from resume_tailor_harness.profile.store import save_facts
from resume_tailor_harness.services import agent_applications as service
from resume_tailor_harness.services.config_store import YamlConfigStore
from resume_tailor_harness.tenancy.system_db import User
from resume_tailor_harness.tenancy.workspace import provision_workspace
from resume_tailor_harness.tracking.tables import (
    Application,
    ApplicationEvent,
    ApplicationQuestion,
    CoverLetter,
    Job,
    ResumeVersion,
    utcnow,
)


@pytest.fixture
def app_client(tmp_path):
    app = create_app(
        db_url="sqlite://", data_dir=tmp_path / "data", config_dir=tmp_path / "config"
    )
    with TestClient(app) as client:
        yield app, client


def seed_job(app, **values):
    with Session(app.state.engine) as session:
        job = Job(
            source="manual",
            title="Engineer",
            company="Example",
            jd_text="Full JD\nWith details",
            **values,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.id is not None
        return job.id


def test_queue_excludes_unapproved_archived_and_all_submission_history(app_client):
    app, client = app_client
    expected = [
        seed_job(app, status=status) for status in ("approved", "tailored", "rendered")
    ]
    for status in ("raw", "shortlisted", "rejected"):
        seed_job(app, status=status)
    seed_job(app, status="approved", archived_at=utcnow())
    with Session(app.state.engine) as session:
        session.add(Application(job_id=expected[1]))
        session.commit()
    for status in (
        "submitted",
        "interview",
        "offer",
        "rejected",
        "closed",
        "timestamp",
        "event",
    ):
        job_id = seed_job(app, status="approved")
        with Session(app.state.engine) as session:
            app_row = Application(
                job_id=job_id,
                status="ready" if status in {"timestamp", "event"} else status,
                submitted_at=utcnow() if status == "timestamp" else None,
            )
            session.add(app_row)
            session.commit()
            if status == "event":
                session.refresh(app_row)
                assert app_row.id is not None
                session.add(
                    ApplicationEvent(
                        application_id=app_row.id, kind="application_submitted"
                    )
                )
                session.commit()
        blocked = client.get(f"/api/jobs/{job_id}/application-context")
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "APPLICATION_NOT_READY"
    first = client.get("/api/application-jobs?pageSize=2")
    assert first.headers["cache-control"] == "no-store"
    assert [job["jobId"] for job in first.json()["data"]] == expected[:2]
    assert first.json()["pagination"] == {
        "page": 1,
        "pageSize": 2,
        "totalItems": 3,
        "totalPages": 2,
    }
    assert (
        client.get("/api/application-jobs?pageSize=2&page=2").json()["data"][0]["jobId"]
        == expected[2]
    )
    assert client.get("/api/application-jobs?page=0").status_code == 422
    assert client.get("/api/application-jobs?pageSize=201").status_code == 422
    assert client.get("/api/jobs/999/application-context").status_code == 404


def test_profile_patch_preserves_fields_and_rejects_stale_or_unconfirmed_updates(
    app_client,
):
    _, client = app_client
    client.put(
        "/api/config/application-profile", json={"fullName": "Existing", "phone": "555"}
    )
    snapshot = client.get("/api/application-profile").json()
    body = {
        "revision": snapshot["revision"],
        "profile": {
            "email": "  updated@example.com  ",
            "industryExperience": " 3 years, confirmed 2026-10-23 ",
            "codingPreference": "80%",
            "technicalDomain": "Full Stack",
            "officeAttendance": "U.S., Example City, 3 days per week: Yes",
            "employerScreeningAnswers": "Acme / REQ-1: start 2026-11-23",
        },
        "userConfirmed": True,
    }
    response = client.patch("/api/application-profile", json=body)
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    assert response.json()["profile"]["fullName"] == "Existing"
    assert response.json()["profile"]["email"] == "updated@example.com"
    assert response.json()["profile"]["industryExperience"] == (
        "3 years, confirmed 2026-10-23"
    )
    for key in (
        "codingPreference",
        "technicalDomain",
        "officeAttendance",
        "employerScreeningAnswers",
    ):
        assert response.json()["profile"][key] == body["profile"][key]
    stale = client.patch("/api/application-profile", json=body)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "PROFILE_STALE"
    body["revision"] = response.json()["revision"]
    for changes in ({"email": None}, {"invented": "value"}, {"email": "x" * 4001}):
        assert (
            client.patch(
                "/api/application-profile", json={**body, "profile": changes}
            ).status_code
            == 422
        )
    for confirmation in (False, "true", 1, None):
        assert (
            client.patch(
                "/api/application-profile", json={**body, "userConfirmed": confirmation}
            ).status_code
            == 422
        )
    cleared = client.patch(
        "/api/application-profile", json={**body, "profile": {"phone": ""}}
    )
    assert cleared.status_code == 200
    assert client.get("/api/config/application-profile").json()["phone"] == ""


def test_profile_compare_and_swap_across_store_instances(tmp_path):
    store = YamlConfigStore(tmp_path)
    snapshot = service.read_profile(store)

    def change(name):
        try:
            service.update_profile(
                YamlConfigStore(tmp_path),
                ApplicationProfileUpdate(
                    revision=snapshot.revision,
                    profile=ApplicationProfilePatch(full_name=name),
                    user_confirmed=True,
                ),
            )
            return "saved"
        except service.ApplicationWorkflowError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, ["First", "Second"]))
    assert sorted(results) == ["PROFILE_STALE", "saved"]


def test_questions_are_idempotent_scoped_and_confirmed_with_revision(app_client):
    app, client = app_client
    one = seed_job(app, status="approved")
    two = seed_job(app, status="approved")
    question = {
        "question": "  Have you worked here?  ",
        "jobId": one,
        "context": "Employer: Example",
    }
    created = client.post("/api/application-questions", json=question).json()
    assert created["answer"] is None and created["question"] == "Have you worked here?"
    assert (
        client.post("/api/application-questions", json=question).json()["id"]
        == created["id"]
    )
    route = f"/api/application-questions/{created['id']}"
    for invalid in (
        {"answer": "No", "revision": 1},
        {"answer": "No", "revision": 1, "userConfirmed": False},
        {"answer": "   ", "revision": 1, "userConfirmed": True},
    ):
        assert client.patch(route, json=invalid).status_code == 422
    answered = client.patch(
        route, json={"answer": "No", "revision": 1, "userConfirmed": True}
    )
    assert answered.status_code == 200 and answered.json()["revision"] == 2
    assert client.get(route).json()["answer"] == "No"
    assert (
        client.post("/api/application-questions", json=question).json()["answer"]
        == "No"
    )
    stale = client.patch(
        route, json={"answer": "Yes", "revision": 1, "userConfirmed": True}
    )
    assert (
        stale.status_code == 409 and stale.json()["error"]["code"] == "QUESTION_STALE"
    )
    global_question = client.post(
        "/api/application-questions",
        json={"question": "Preferred name?", "scope": "profile"},
    ).json()
    assert (
        client.get(f"/api/application-questions?jobId={one}&status=answered").json()[
            "pagination"
        ]["totalItems"]
        == 1
    )
    other = client.get(f"/api/application-questions?jobId={two}").json()["data"]
    assert [q["id"] for q in other] == [global_question["id"]]
    assert (
        client.get("/api/application-questions?pageSize=1&page=2").json()["data"][0][
            "id"
        ]
        == global_question["id"]
    )
    first_context = client.get(f"/api/jobs/{one}/application-context").json()
    assert "Answer: No" in first_context["prompt"]
    assert (
        "Have you worked here?"
        not in client.get(f"/api/jobs/{two}/application-context").json()["prompt"]
    )
    assert (
        "Have you worked here?"
        in client.get(f"/api/jobs/{one}/application-prompt").json()["prompt"]
    )
    assert (
        client.patch(
            route, json={"answer": None, "revision": 2, "userConfirmed": True}
        ).json()["answer"]
        is None
    )
    for invalid in (
        {"question": "?"},
        {"question": "?", "scope": "profile", "jobId": one},
        {"question": " ", "jobId": one},
        {"question": "?", "jobId": one, "answer": "inferred"},
    ):
        assert (
            client.post("/api/application-questions", json=invalid).status_code == 422
        )
    assert (
        client.post(
            "/api/application-questions", json={"question": "?", "jobId": 999}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/application-questions/999",
            json={"answer": "No", "revision": 1, "userConfirmed": True},
        ).status_code
        == 404
    )


def test_context_is_complete_read_only_and_lists_only_safe_attachments(
    app_client, tmp_path
):
    app, client = app_client
    job_id = seed_job(app, status="approved", url="https://example.com/apply")
    facts = ProfileFacts(
        contact=Contact(name="Resume Name"),
        skills={
            "Tools": [
                Skill(name="Python"),
                Skill(
                    name="Guessed",
                    inferred=True,
                    category="hard",
                    evidence_fact_ids=["fact"],
                ),
            ]
        },
    )
    save_facts(facts, app.state.data_dir / "profile" / "facts.json")
    client.put(
        "/api/config/application-profile",
        json={"fullName": "Confirmed Name", "workAuthorization": "User's answer"},
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = output_dir / "resume.pdf"
    pdf.write_bytes(b"%PDF-test")
    with Session(app.state.engine) as session:
        for passed, path in (
            (True, str(pdf)),
            (False, str(pdf)),
            (True, str(tmp_path / "missing.pdf")),
        ):
            session.add(
                ResumeVersion(job_id=job_id, fact_check_passed=passed, pdf_path=path)
            )
        session.add(
            CoverLetter(job_id=job_id, fact_check_passed=True, pdf_path=str(pdf))
        )
        session.commit()
    response = client.get(f"/api/jobs/{job_id}/application-context")
    assert response.status_code == 200, response.text
    context = response.json()
    assert context["job"]["jdText"] == "Full JD\nWith details"
    assert "> Full JD\n> With details" in context["prompt"]
    assert (
        "Confirmed Name" in context["prompt"] and "Resume Name" not in context["prompt"]
    )
    assert "Python" in context["prompt"] and "Guessed" not in context["prompt"]
    assert "Stop before final submission" in context["prompt"]
    assert context["submissionPolicy"] == "stop_before_submit"
    assert (
        context["profileRevision"]
        == client.get("/api/application-profile").json()["revision"]
    )
    assert len(context["attachments"]) == 3
    assert len([a for a in context["attachments"] if a["downloadPath"]]) == 2
    assert str(pdf) not in response.text
    with Session(app.state.engine) as session:
        assert not session.exec(select(Application)).all()
        assert not session.exec(select(ApplicationQuestion)).all()
        job = session.get(Job, job_id)
        assert job is not None and job.status == "approved"


def test_context_rejects_a_passing_flag_with_a_failed_fact_review(app_client):
    app, client = app_client
    job_id = seed_job(app, status="tailored")
    with Session(app.state.engine) as session:
        version = ResumeVersion(
            job_id=job_id,
            fact_check_passed=True,
            gate_reviewers_json=[],
            critique_json=[{"reviewer": "fact-check", "score": 0, "passed": False}],
        )
        session.add(version)
        session.commit()

    context = client.get(f"/api/jobs/{job_id}/application-context")
    assert context.status_code == 200, context.text
    assert context.json()["attachments"] == []
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["resumeVersions"][0]["factCheckPassed"] is False
    assert detail["resumeVersions"][0]["failedGates"] == ["fact-check"]
    assert detail["needsAttention"] is True


def test_sdk_pat_workflow_and_tenant_isolation(mu_app, mu_client):
    for path in (
        "/api/application-jobs",
        "/api/application-profile",
        "/api/application-questions",
        "/api/jobs/1/application-context",
    ):
        assert mu_client.get(path).status_code == 401
    mu_client.post(
        "/api/auth/login", json={"identifier": "owner", "password": "owner-password"}
    )
    token = mu_client.post("/api/account/tokens", json={"name": "applications"}).json()
    mu_client.cookies.clear()
    job_id = seed_job(mu_app, status="approved")

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
        assert [job["jobId"] for job in sdk.iter_application_jobs(page_size=1)] == [
            job_id
        ]
        snapshot = sdk.get_application_profile()
        sdk.update_application_profile(
            {"fullName": "Private Owner"},
            revision=snapshot["revision"],
            user_confirmed=True,
        )
        question = sdk.record_application_question("Private question?", job_id=job_id)
        sdk.answer_application_question(
            question["id"],
            "Private answer",
            revision=question["revision"],
            user_confirmed=True,
        )
        assert len(list(sdk.iter_application_questions(job_id=job_id))) == 1
        assert (
            sdk.get_application_question(question["id"])["answer"] == "Private answer"
        )
        assert "Private answer" in sdk.application_prompt(job_id)
        assert (
            sdk.application_context(job_id)["profile"].get("fullName")
            == "Private Owner"
        )
        with SystemSession(mu_app.state.system_engine) as session:
            session.add(
                User(
                    id="applicant2",
                    username="alice",
                    password_hash=hash_password("alice-password"),
                )
            )
            session.commit()
        provision_workspace(
            mu_app.state.data_dir,
            "applicant2",
            template_dir=mu_app.state.template_config_dir,
        )
        mu_client.post(
            "/api/auth/login",
            json={"identifier": "alice", "password": "alice-password"},
        )
        assert (
            mu_client.get("/api/application-profile").json()["profile"]["fullName"]
            == ""
        )
        assert not mu_client.get("/api/application-jobs").json()["data"]
        assert not mu_client.get("/api/application-questions").json()["data"]
        assert (
            mu_client.get(f"/api/jobs/{job_id}/application-context").status_code == 404
        )
        assert (
            mu_client.patch(
                f"/api/application-questions/{question['id']}",
                json={"revision": 2, "answer": "stolen", "userConfirmed": True},
            ).status_code
            == 404
        )
        mu_client.cookies.clear()
        assert "Private answer" in sdk.application_prompt(job_id)
        mu_client.delete(
            f"/api/account/tokens/{token['id']}",
            headers={"Authorization": f"Bearer {token['token']}"},
        )
        with pytest.raises(APIError) as exc:
            sdk.list_application_jobs()
        assert exc.value.status_code == 401


def test_questions_survive_database_init_and_job_delete_preserves_global_answers(
    app_client,
):
    app, client = app_client
    job_id = seed_job(app, status="raw")
    job_question = client.post(
        "/api/application-questions",
        json={"question": "Employer question?", "jobId": job_id},
    ).json()
    global_question = client.post(
        "/api/application-questions",
        json={"question": "Preferred name?", "scope": "profile"},
    ).json()
    init_db(app.state.engine)
    assert (
        client.get(f"/api/application-questions/{job_question['id']}").status_code
        == 200
    )
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert (
        client.get(f"/api/application-questions/{job_question['id']}").status_code
        == 404
    )
    assert (
        client.get(f"/api/application-questions/{global_question['id']}").status_code
        == 200
    )


def test_question_answers_compare_and_swap_across_sessions(tmp_path):
    from resume_tailor_harness.api.schemas.agent_applications import (
        ApplicationQuestionCreate,
        ApplicationQuestionUpdate,
    )
    from resume_tailor_harness.db import make_engine

    engine = make_engine(f"sqlite:///{(tmp_path / 'questions.db').as_posix()}")
    init_db(engine)
    with Session(engine) as session:
        question = service.create_question(
            session,
            ApplicationQuestionCreate(question="Preferred name?", scope="profile"),
        )

    def change(answer):
        with Session(engine) as session:
            try:
                service.update_question(
                    session,
                    question.id,
                    ApplicationQuestionUpdate(
                        revision=question.revision,
                        answer=answer,
                        user_confirmed=True,
                    ),
                )
                return "saved"
            except service.ApplicationWorkflowError as exc:
                return exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(change, ["First", "Second"]))
        assert sorted(results) == ["QUESTION_STALE", "saved"]
    finally:
        engine.dispose()
