import io
import tarfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as SystemSession

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.auth import hash_password
from resume_tailor_harness.db import get_session
from resume_tailor_harness.models.profile import (
    Bullet,
    Contact,
    Education,
    Experience,
    ProfileFacts,
    Skill,
)
from resume_tailor_harness.profile.store import save_facts
from resume_tailor_harness.tracking.tables import Job
from resume_tailor_harness.tenancy.system_db import User
from resume_tailor_harness.tenancy.workspace import provision_workspace


@pytest.fixture
def app_client(tmp_path):
    app = create_app(
        db_url="sqlite://", data_dir=tmp_path / "data", config_dir=tmp_path / "config"
    )
    with TestClient(app) as client:
        with get_session(app.state.engine) as session:
            job = Job(
                source="manual",
                title="Software Engineer",
                company="Acme",
                url="https://example.com/apply/42",
                jd_text="Build Python services.",
                criteria_json={
                    "must_have_skills": ["PY", "Rust", "Leadership"],
                    "salary_range": {"minimum": 90000, "currency": "USD"},
                },
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            job_id = job.id
        yield client, job_id, tmp_path


def prompt_from(response):
    assert response.status_code == 200
    return response.json()["prompt"]


def test_prompt_combines_resume_and_explicit_answers_without_inference(app_client):
    client, job_id, tmp_path = app_client
    save_facts(
        ProfileFacts(
            contact=Contact(
                name="Ada Resume", email="ada@example.com", location="Boston"
            ),
            education=[
                Education(institution="Example University", degree="BS", field="CS")
            ],
            experience=[
                Experience(
                    company="Old Co",
                    title="Engineer",
                    start="2020-01",
                    bullets=[
                        Bullet(text="Built Python services", source_ref="private/path")
                    ],
                )
            ],
            skills={
                "Languages": [
                    Skill(name="Python", aliases=["PY"]),
                    Skill(
                        name="Leadership",
                        inferred=True,
                        category="soft",
                        evidence_fact_ids=["x"],
                    ),
                ]
            },
        ),
        tmp_path / "data/profile/facts.json",
    )
    saved = client.put(
        "/api/config/application-profile",
        json={
            "fullName": "  Ada Application  ",
            "expectedSalary": "USD 140,000 base/year",
            "sponsorshipNeeded": "Yes, in the future",
            "ethnicity": "Prefer not to disclose",
        },
    )
    assert saved.status_code == 200
    response = client.get(f"/api/jobs/{job_id}/application-prompt")
    assert response.headers["cache-control"] == "no-store"
    prompt = prompt_from(response)
    assert prompt.startswith("# Job application\n\nOpen the application link")
    assert "- Full name: Ada Application" in prompt
    assert "- Email: ada@example.com" in prompt
    assert "- Expected salary: USD 140,000 base/year" in prompt
    assert "- Sponsorship needed: Yes, in the future" in prompt
    assert "- Race / ethnicity: Prefer not to disclose" in prompt
    assert "Disability status:" not in prompt
    assert "Relocation preference:" not in prompt
    assert "- Skills matching this job: PY\n" in prompt
    assert "### BS in CS — Example University" in prompt
    assert "### Engineer — Old Co\n- Dates: From 2020-01" in prompt
    assert "- Built Python services" in prompt
    assert "Leadership" not in prompt  # An inferred skill is not an answer.
    assert "Rust" not in prompt  # Employer requirements are not qualifications.
    assert "90000" not in prompt
    assert "Build Python services." not in prompt  # No redundant job-description dump.
    assert "Not provided" not in prompt
    assert '"education":' not in prompt
    assert "private/path" not in response.text
    assert "Stop before final submission" in response.json()["prompt"]
    assert "- Application link: https://example.com/apply/42" in prompt


def test_missing_profile_and_search_defaults_are_not_application_answers(app_client):
    client, job_id, _ = app_client
    client.put(
        "/api/config/search", json={"minSalary": 90000, "sponsorshipRequired": False}
    )
    prompt = prompt_from(client.get(f"/api/jobs/{job_id}/application-prompt"))
    assert "## Applicant" not in prompt
    assert "## Education" not in prompt
    assert "## Application answers" not in prompt
    assert "## Voluntary self-identification" not in prompt
    assert "Sponsorship needed:" not in prompt
    assert "Expected salary:" not in prompt
    assert "90000" not in prompt
    assert "Ask me for required missing information" in prompt
    assert "leave unanswered optional fields blank" in prompt
    assert client.get("/api/jobs/99999/application-prompt").status_code == 404


def test_answers_persist_can_be_cleared_and_validate_lengths(app_client):
    client, _, tmp_path = app_client
    route = "/api/config/application-profile"
    assert all(value == "" for value in client.get(route).json().values())
    assert (
        client.put(route, json={"veteranStatus": "No", "phone": "123"}).status_code
        == 200
    )
    assert client.get(route).json()["veteranStatus"] == "No"
    assert (tmp_path / "config/application_profile.yaml").is_file()
    assert client.put(route, json={"phone": "x" * 4001}).status_code == 422
    assert client.get(route).json()["phone"] == "123"
    assert client.put(route, json={}).status_code == 200
    assert client.get(route).json()["veteranStatus"] == ""


def test_common_screening_answers_roundtrip_into_prompt_and_can_be_cleared(app_client):
    client, job_id, _ = app_client
    route = "/api/config/application-profile"
    answers = {
        "atLeast18": "Yes",
        "usWorkerCategory": "No",
        "workAuthorizationVerification": "U.S.: Yes",
        "terminationHistory": "No",
        "exportControlCitizenship": "Cuba, Iran, North Korea, Syria: No",
        "plannedBoardMembership": "No",
        "currentBoardMembership": "No",
        "governmentEmployment": "U.S. federal/state/local; last 5 years: No",
        "referralSources": "Acme: LinkedIn",
        "previousEmployment": "Acme: No",
        "previousApplications": "Acme: No",
        "employerRelationships": "Acme: No",
    }
    assert all(client.get(route).json()[key] == "" for key in answers)
    saved = client.put(
        route, json={key: f"  {value}  " for key, value in answers.items()}
    )
    assert saved.status_code == 200
    for key, value in answers.items():
        assert saved.json()[key] == value
        assert client.get(route).json()[key] == value
    prompt = prompt_from(client.get(f"/api/jobs/{job_id}/application-prompt"))
    assert "## Common screening answers" in prompt
    assert "## Employer-specific answers" in prompt
    assert "- Previous employment with the employer: Acme: No" in prompt
    assert "- Can provide verification of legal right to work: U.S.: Yes" in prompt
    assert "- At least 18 years old: Yes" in prompt
    assert (
        client.put(route, json={"exportControlCitizenship": "x" * 4001}).status_code
        == 422
    )
    assert (
        client.get(route).json()["exportControlCitizenship"]
        == answers["exportControlCitizenship"]
    )
    assert client.put(route, json={}).status_code == 200
    assert all(client.get(route).json()[key] == "" for key in answers)
    cleared = prompt_from(client.get(f"/api/jobs/{job_id}/application-prompt"))
    assert "## Common screening answers" not in cleared
    assert "## Employer-specific answers" not in cleared


def test_hosted_endpoints_require_authentication(mu_client):
    assert mu_client.get("/api/config/application-profile").status_code == 401
    assert mu_client.put("/api/config/application-profile", json={}).status_code == 401
    assert mu_client.get("/api/jobs/1/application-prompt").status_code == 401


def test_hosted_profiles_jobs_and_facts_are_isolated_and_resettable(mu_app, mu_client):
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
    route = "/api/config/application-profile"

    def login(name, password):
        assert (
            mu_client.post(
                "/api/auth/login", json={"identifier": name, "password": password}
            ).status_code
            == 200
        )

    login("owner", "owner-password")
    assert (
        mu_client.put(
            route,
            json={"fullName": "Private Owner", "disabilityStatus": "Owner answer"},
        ).status_code
        == 200
    )
    owner_job = mu_client.post(
        "/api/jobs", json={"jdText": "Owner job", "title": "Owner role"}
    ).json()["id"]
    save_facts(
        ProfileFacts(
            contact=Contact(name="Owner resume"), summary="Private resume summary"
        ),
        mu_app.state.default_context.paths.profile_dir / "facts.json",
    )
    assert (
        "Private resume summary"
        in mu_client.get(f"/api/jobs/{owner_job}/application-prompt").text
    )

    login("alice", "alice-password")
    assert mu_client.get(route).json()["fullName"] == ""
    assert mu_client.get(f"/api/jobs/{owner_job}/application-prompt").status_code == 404
    alice_job = mu_client.post(
        "/api/jobs", json={"jdText": "Alice job", "title": "Alice role"}
    ).json()["id"]
    response = mu_client.get(f"/api/jobs/{alice_job}/application-prompt")
    assert "Private Owner" not in response.text
    assert "Private resume summary" not in response.text
    assert "- Role: Alice role" in prompt_from(response)

    login("owner", "owner-password")
    archive = mu_client.get("/api/settings/bundle").content
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        entry = bundle.extractfile("config/application_profile.yaml")
        assert entry is not None and b"Private Owner" in entry.read()
    assert (
        mu_client.post("/api/settings/sections/application_profile/reset").status_code
        == 200
    )
    assert mu_client.get(route).json()["disabilityStatus"] == ""
    assert (
        mu_client.post(
            "/api/settings/bundle?confirm=APPLY",
            files={"file": ("settings.tar.gz", archive, "application/gzip")},
        ).status_code
        == 200
    )
    assert mu_client.get(route).json()["fullName"] == "Private Owner"
