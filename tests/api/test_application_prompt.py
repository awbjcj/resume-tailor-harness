import io
import tarfile

import pytest
import yaml
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
    empty = client.get(route).json()
    assert empty["phone"] == "" and empty["sex"] == ""
    assert empty["workEligibility"] == [] and empty["employerAnswers"] == []
    assert empty["aiMatchingPreference"] == "unknown"
    assert empty["sexConfirmedOn"] is None
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


def test_structured_answers_keep_scope_dates_unknowns_and_actual_degrees(app_client):
    client, job_id, tmp_path = app_client
    save_facts(
        ProfileFacts(
            contact=Contact(name="Ada"),
            education=[Education(institution="Example University", degree="MEng")],
        ),
        tmp_path / "data/profile/facts.json",
    )
    response = client.put(
        "/api/config/application-profile",
        json={
            "fullName": "Ada Existing",
            "previousEmployment": "Acme: No; Other: Yes",
            "legalName": {"givenName": " Ada ", "familyName": "Lovelace"},
            "mailingAddress": {
                "line1": "1 Example Street",
                "postalCode": "00123",
                "country": "US",
            },
            "alternateEmails": [
                {
                    "email": "ada@acme.example",
                    "employer": "Acme",
                    "permitted": True,
                    "confirmedOn": "2026-10-20",
                },
                {
                    "email": "hidden@other.example",
                    "employer": "Other",
                    "permitted": True,
                    "confirmedOn": "2026-10-20",
                },
            ],
            "workEligibility": [
                {
                    "country": "US",
                    "immigrationStatus": " H-1B ",
                    "authorizedToWork": True,
                    "sponsorshipNow": True,
                    "sponsorshipFuture": None,
                    "currentlyOnOpt": False,
                    "stemOptExtensionEligible": False,
                    "confirmedOn": "2026-10-20",
                },
                {
                    "country": "IN",
                    "authorizedToWork": False,
                    "confirmedOn": "2026-10-21",
                },
            ],
            "experienceRanges": [
                {
                    "specialty": "Software and AI",
                    "minimumYears": 3,
                    "maximumYears": 6,
                    "confirmedOn": "2026-10-20",
                }
            ],
            "sex": "Male",
            "sexConfirmedOn": "2026-10-20",
            "gender": "Self-described gender",
            "aiMatchingPreference": "opt_in",
            "aiMatchingConfirmedOn": "2026-10-20",
            "employerAnswers": [
                {
                    "employer": " acme ",
                    "requisition": "REQ-42",
                    "country": "US",
                    "category": "degree_category",
                    "question": "Category for MEng at Example University?",
                    "answer": "Master of Science category only",
                    "confirmedOn": "2026-10-20",
                    "timeframe": "This application",
                },
                {
                    "employer": "Acme",
                    "question": "Contractor here in the last 12 months?",
                    "answer": None,
                    "confirmedOn": "2026-10-20",
                },
                {
                    "employer": "Other",
                    "question": "Other employer secret",
                    "answer": "Hidden",
                    "confirmedOn": "2026-10-20",
                },
                {
                    "employer": "Acme",
                    "question": "Old rolling count?",
                    "answer": "1",
                    "confirmedOn": "2000-01-01",
                    "validUntil": "2000-02-01",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    profile = client.get("/api/config/application-profile").json()
    assert profile["legalName"]["givenName"] == "Ada"
    assert profile["legalName"]["middleName"] == ""
    assert profile["mailingAddress"]["postalCode"] == "00123"
    assert profile["workEligibility"][0]["currentlyOnOpt"] is False
    assert profile["workEligibility"][0]["sponsorshipFuture"] is None
    prompt = prompt_from(client.get(f"/api/jobs/{job_id}/application-prompt"))
    assert "- Legal given name: Ada" in prompt
    assert "- Postal code: 00123" in prompt
    assert "ada@acme.example" in prompt and "hidden@other.example" not in prompt
    assert "### US\n- Immigration status: H-1B" in prompt
    assert "- Currently on OPT: No" in prompt
    assert "- Needs sponsorship in the future: Unknown" in prompt
    assert "### IN\n- Legally authorized to work: No" in prompt
    assert (
        "- Relevant professional experience: 3–6 years\n- Confirmed on: 2026-10-20"
        in prompt
    )
    assert "- Sex (optional self-identification): Male" in prompt
    assert "- Gender: Self-described gender" in prompt
    assert "- AI-assisted candidate matching: Opt in" in prompt
    assert "- Requisition (must match): REQ-42" in prompt
    assert "- Applicable timeframe: This application" in prompt
    assert "- Answer: Unknown — ask if required" in prompt
    assert "Other employer secret" not in prompt
    assert "- Reuse: Expired — ask again" in prompt
    assert "### MEng — Example University" in prompt
    assert "Master of Science category only" in prompt
    assert "Never advance totals with time" in prompt
    assert "Saved answers never authorize accepting terms" in prompt


@pytest.mark.parametrize(
    "invalid",
    [
        {
            "workEligibility": [
                {"country": "US", "confirmedOn": "2026-10-20", "currentlyOnOpt": "no"}
            ]
        },
        {"workEligibility": [{"country": "US", "confirmedOn": "not-a-date"}]},
        {"workEligibility": [{"country": " ", "confirmedOn": "2026-10-20"}]},
        {"workEligibility": [{"country": "US"}]},
        {
            "experienceRanges": [
                {
                    "specialty": "AI",
                    "minimumYears": 6,
                    "maximumYears": 3,
                    "confirmedOn": "2026-10-20",
                }
            ]
        },
        {
            "experienceRanges": [
                {"specialty": "AI", "minimumYears": 3, "confirmedOn": "2026-10-20"}
            ]
        },
        {"alternateEmails": [{"email": "invalid", "confirmedOn": "2026-10-20"}]},
        {
            "alternateEmails": [
                {
                    "email": "ada@example.com",
                    "requisition": "42",
                    "confirmedOn": "2026-10-20",
                }
            ]
        },
        {
            "employerAnswers": [
                {
                    "employer": "Acme",
                    "question": "Question?",
                    "answer": "x" * 4001,
                    "confirmedOn": "2026-10-20",
                }
            ]
        },
        {
            "employerAnswers": [
                {
                    "employer": "Acme",
                    "question": "Question?",
                    "confirmedOn": "2026-10-20",
                    "validUntil": "2026-10-19",
                }
            ]
        },
        {"legalName": {"guessedName": "Ada"}},
        {"aiMatchingPreference": "yes"},
    ],
)
def test_invalid_structured_answers_do_not_replace_saved_profile(app_client, invalid):
    client, _, _ = app_client
    route = "/api/config/application-profile"
    client.put(route, json={"fullName": "Existing answer"})
    assert client.put(route, json=invalid).status_code == 422
    assert client.get(route).json()["fullName"] == "Existing answer"


def test_legacy_notes_are_preserved_without_guessing_structured_answers(app_client):
    client, _, tmp_path = app_client
    path = tmp_path / "config/application_profile.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "full_name": "Ada Example",
                "gender": "Female",
                "additional_answers": "US: visa notes; AI matching: yes for Acme only",
                "employer_screening_answers": "Acme / REQ-42: role requirements Yes",
                "runtime_key": "preserve me",
            }
        ),
        encoding="utf-8",
    )
    response = client.get("/api/config/application-profile")
    assert response.status_code == 200
    profile = response.json()
    assert profile["legalName"]["givenName"] == ""
    assert profile["sex"] == "" and profile["workEligibility"] == []
    assert profile["aiMatchingPreference"] == "unknown"
    assert profile["employerAnswers"] == []
    saved = client.put(
        "/api/config/application-profile", json={**profile, "phone": "123"}
    )
    assert saved.status_code == 200
    assert saved.json()["additionalAnswers"] == profile["additionalAnswers"]
    assert (
        saved.json()["employerScreeningAnswers"] == profile["employerScreeningAnswers"]
    )
    assert (
        yaml.safe_load(path.read_text(encoding="utf-8"))["runtime_key"] == "preserve me"
    )


def test_prompt_reads_current_search_preferences_without_copying_them_to_profile(
    app_client,
):
    client, job_id, _ = app_client
    search_route = "/api/config/search"
    profile_route = "/api/config/application-profile"
    prompt_route = f"/api/jobs/{job_id}/application-prompt"
    assert (
        client.put(
            search_route,
            json={
                "sponsorshipRequired": True,
                "remotePolicy": ["hybrid", "onsite"],
                "minSalary": 130000,
            },
        ).status_code
        == 200
    )
    prompt = prompt_from(client.get(prompt_route))
    assert "- Sponsorship needed: Yes (saved Search setting" in prompt
    assert "Hybrid; On-site (saved Search settings)" in prompt
    assert "Expected salary:" not in prompt
    profile = client.get(profile_route).json()
    assert profile["sponsorshipNeeded"] == ""
    assert profile["remotePreference"] == ""

    assert (
        client.put(
            search_route,
            json={"sponsorshipRequired": False, "remotePolicy": ["remote"]},
        ).status_code
        == 200
    )
    updated = prompt_from(client.get(prompt_route))
    assert "Sponsorship needed:" not in updated
    assert "Remote (saved Search settings)" in updated
    assert "Hybrid; On-site" not in updated


def test_common_screening_answers_roundtrip_into_prompt_and_can_be_cleared(app_client):
    client, job_id, _ = app_client
    route = "/api/config/application-profile"
    answers = {
        "industryExperience": "3 years, confirmed 2026-10-23",
        "codingPreference": "80% of my time coding",
        "technicalDomain": "Full Stack",
        "officeAttendance": "U.S., Example City office, 3 days per week: Yes",
        "employerScreeningAnswers": "Acme / REQ-1: start 2026-11-23; confirmed 2026-10-23",
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
    assert "## Professional screening" in prompt
    assert "- Coding time preference: 80% of my time coding" in prompt
    assert "Acme / REQ-1: start 2026-11-23; confirmed 2026-10-23" in prompt
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
    assert "## Professional screening" not in cleared
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
            "/api/config/search",
            json={"sponsorshipRequired": True, "remotePolicy": ["hybrid"]},
        ).status_code
        == 200
    )
    assert (
        mu_client.put(
            route,
            json={
                "fullName": "Private Owner",
                "disabilityStatus": "Owner answer",
                "workEligibility": [
                    {
                        "country": "US",
                        "authorizedToWork": False,
                        "confirmedOn": "2026-10-20",
                    }
                ],
                "employerAnswers": [
                    {
                        "employer": "Private Co",
                        "question": "Private question?",
                        "answer": "Private answer",
                        "confirmedOn": "2026-10-20",
                    }
                ],
            },
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
    owner_prompt = prompt_from(
        mu_client.get(f"/api/jobs/{owner_job}/application-prompt")
    )
    assert "Hybrid (saved Search settings)" in owner_prompt
    assert "- Sponsorship needed: Yes (saved Search setting" in owner_prompt

    login("alice", "alice-password")
    assert (
        mu_client.put(
            "/api/config/search", json={"remotePolicy": ["remote"]}
        ).status_code
        == 200
    )
    assert mu_client.get(route).json()["fullName"] == ""
    assert mu_client.get(route).json()["employerAnswers"] == []
    assert mu_client.get(route).json()["workEligibility"] == []
    assert mu_client.get(f"/api/jobs/{owner_job}/application-prompt").status_code == 404
    alice_job = mu_client.post(
        "/api/jobs", json={"jdText": "Alice job", "title": "Alice role"}
    ).json()["id"]
    response = mu_client.get(f"/api/jobs/{alice_job}/application-prompt")
    assert "Private Owner" not in response.text
    assert "Private resume summary" not in response.text
    assert "- Role: Alice role" in prompt_from(response)
    assert "Hybrid (saved Search settings)" not in prompt_from(response)
    assert "Sponsorship needed:" not in prompt_from(response)
    assert "Remote (saved Search settings)" in prompt_from(response)

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
    assert mu_client.get(route).json()["employerAnswers"] == []
    assert (
        mu_client.post(
            "/api/settings/bundle?confirm=APPLY",
            files={"file": ("settings.tar.gz", archive, "application/gzip")},
        ).status_code
        == 200
    )
    assert mu_client.get(route).json()["fullName"] == "Private Owner"
    restored = mu_client.get(route).json()
    assert restored["workEligibility"][0]["authorizedToWork"] is False
    assert restored["workEligibility"][0]["confirmedOn"] == "2026-10-20"
    assert restored["employerAnswers"][0]["answer"] == "Private answer"
