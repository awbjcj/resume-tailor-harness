from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.db import get_session
from resume_tailor_harness.discovery import pipeline
from resume_tailor_harness.discovery.ingest import IngestOutcome, save_or_upgrade
from resume_tailor_harness.discovery.search_config import SearchConfig
from resume_tailor_harness.models.job import JobCriteria, Seniority
from resume_tailor_harness.models.profile import Contact, ProfileFacts
from resume_tailor_harness.services import discovery
from resume_tailor_harness.tracking.tables import Job


@pytest.fixture
def client():
    with TestClient(create_app(db_url="sqlite://")) as client:
        yield client


def full_job():
    return {
        "title": "  Platform Engineer  ",
        "company": "Acme",
        "jdText": "Build Python services.\nSupport customers and improve reliability.",
        "url": "https://example.com/jobs/42",
        "location": "Boston, MA; New York, NY",
        "postedAt": "2026-10-01T00:00:00Z",
        "details": {
            "applicationUrl": "https://apply.example.com/42",
            "postingId": "REQ-42",
            "closesAt": "2026-11-30",
            "remotePolicy": "hybrid",
            "remoteRestrictions": "United States",
            "attendance": "Two days per week",
            "employmentType": "full_time",
            "seniority": "senior",
            "sponsorshipSignal": "offered",
            "yoeMin": 5,
            "industry": "Software",
            "companySize": "201-500",
            "techStack": ["Python", "SQL"],
            "mustHaveSkills": ["Distributed systems"],
            "niceToHaveSkills": ["Kubernetes"],
            "salaryMin": 120000,
            "salaryMax": 160000,
            "salaryCurrency": "USD",
            "salaryPeriod": "year",
        },
    }


def test_manual_job_saved_and_listed_without_network_or_extraction(client, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Saving manual jobs must not fetch or extract")

    monkeypatch.setattr(discovery, "job_from_url", unexpected)
    monkeypatch.setattr(discovery, "build_url_extract_agent", unexpected)
    response = client.post("/api/jobs", json=full_job())
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["title"] == "Platform Engineer"
    assert job["source"] == "manual"
    assert job["status"] == "raw"
    assert job["url"] == "https://apply.example.com/42"
    assert job["postedAt"].startswith("2026-10-01")
    assert job["remotePolicy"] == "hybrid"
    assert job["salaryMin"] == 120000
    assert job["employmentType"] == "full_time"
    assert job["criteriaJson"]["must_have_skills"] == ["Distributed systems"]
    assert job["criteriaJson"]["manual_details"]["source_url"] == full_job()["url"]
    assert job["criteriaJson"]["manual_details"]["posting_id"] == "REQ-42"
    assert job["criteriaJson"]["manual_details"]["closes_at"] == "2026-11-30"
    assert any(
        row["jobId"] == job["id"] for row in client.get("/api/triage").json()["data"]
    )
    assert client.get(f"/api/jobs/{job['id']}").json()["jdText"] == full_job()["jdText"]
    assert (
        client.patch(f"/api/jobs/{job['id']}", json={"status": "approved"}).status_code
        == 200
    )


def test_minimal_legacy_request_still_works(client):
    response = client.post("/api/jobs", json={"jdText": "Work on reliable systems"})
    assert response.status_code == 201
    assert response.json()["criteriaJson"] is None
    assert response.json()["url"] is None


def test_invalid_manual_fields_do_not_create_a_job(client, subtests):
    for change in [
        {"jdText": " \n\t "},
        {"url": "javascript:alert(1)"},
        {"url": "https://name:secret@example.com/job"},
        {"postedAt": "not-a-date"},
        {"details": {"salaryMin": -1}},
        {"details": {"salaryMin": "NaN"}},
        {
            "details": {
                "salaryMin": 100,
                "salaryMax": 50,
                "salaryCurrency": "USD",
                "salaryPeriod": "year",
            }
        },
        {"details": {"salaryMin": 100}},
        {"details": {"remotePolicy": "sometimes"}},
        {"details": {"applicationUrl": "file:///secret"}},
        {"details": {"closesAt": "2026-02-30"}},
        {"details": {"yoeMin": 1.5}},
    ]:
        with subtests.test(change=change):
            response = client.post("/api/jobs", json={**full_job(), **change})
            assert response.status_code == 422, response.text
            with get_session(client.app.state.engine) as session:
                assert session.exec(select(Job)).all() == []


def test_duplicate_keeps_progress_and_metadata(client):
    first = client.post("/api/jobs", json=full_job()).json()
    client.patch(f"/api/jobs/{first['id']}", json={"status": "approved"})
    changed = deepcopy(full_job())
    changed["details"]["salaryMin"] = 1
    response = client.post("/api/jobs", json=changed)
    assert response.status_code == 409
    after = client.get(f"/api/jobs/{first['id']}").json()
    assert after["status"] == "approved"
    assert after["criteriaJson"] == first["criteriaJson"]


def test_manual_job_obeys_active_quota(client, monkeypatch):
    monkeypatch.setattr(discovery, "active_limit", lambda *args: 1)
    assert client.post("/api/jobs", json=full_job()).status_code == 201
    response = client.post("/api/jobs", json={"jdText": "A different opportunity"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_manual_facts_survive_a_richer_posting_refresh(client):
    created = client.post("/api/jobs", json=full_job()).json()
    with get_session(client.app.state.engine) as session:
        job = session.get(Job, created["id"])
        assert job is not None and job.criteria_json is not None
        job.status = "extracted"
        job.criteria_json = {**job.criteria_json, "inferred_only": "stale"}
        session.add(job)
        session.commit()
        refreshed, outcome = save_or_upgrade(
            session,
            source="url",
            url=created["url"],
            company="Acme",
            title="Platform Engineer",
            location=created["location"],
            jd_text=full_job()["jdText"]
            + "\nAdditional responsibilities and qualifications." * 30,
        )
        assert outcome is IngestOutcome.upgraded
        assert refreshed is not None and refreshed.criteria_json is not None
        assert refreshed.status == "raw"
        assert "inferred_only" not in refreshed.criteria_json
        assert refreshed.criteria_json["remote_policy"] == "hybrid"
        assert refreshed.criteria_json["manual_details"]["posting_id"] == "REQ-42"


def test_manual_details_survive_extraction_and_leave_unknowns_extractable(
    client, monkeypatch, tmp_path
):
    payload = full_job()
    del payload["details"]["seniority"]
    job_id = client.post("/api/jobs", json=payload).json()["id"]

    async def extract(*args, **kwargs):
        return JobCriteria(
            remote_policy="onsite", seniority=Seniority.staff, tech_stack=["Java"]
        )

    class UnusedRunner:
        def run(self, prompt: str):
            raise AssertionError("extraction was replaced by the test")

        async def arun(self, prompt: str):
            return self.run(prompt)

    monkeypatch.setattr(pipeline, "aextract_job_criteria", extract)
    with get_session(client.app.state.engine) as session:
        pipeline.run_extract(
            session, UnusedRunner(), industry_taxonomy_path=tmp_path / "industries.yaml"
        )
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "extracted"
    assert job["remotePolicy"] == "hybrid"
    assert job["seniority"] == "staff"
    assert job["criteriaJson"]["tech_stack"] == ["Python", "SQL"]
    assert job["criteriaJson"]["manual_details"]["posting_id"] == "REQ-42"

    def discover_after_reset(session, *args, **kwargs):
        reset = session.get(Job, job_id)
        assert reset is not None and reset.criteria_json is not None
        assert reset.status == "raw"
        assert reset.criteria_json["seniority"] is None
        assert reset.criteria_json["remote_policy"] == "hybrid"
        assert reset.criteria_json["manual_details"]["posting_id"] == "REQ-42"
        pipeline.run_extract(
            session, UnusedRunner(), industry_taxonomy_path=tmp_path / "industries.yaml"
        )
        return {}

    monkeypatch.setattr(pipeline, "discover", discover_after_reset)
    with get_session(client.app.state.engine) as session:
        pipeline.reprocess(
            session,
            SearchConfig(),
            ProfileFacts(contact=Contact(name="Test")),
            UnusedRunner(),
            UnusedRunner(),
            ["all"],
        )
    after = client.get(f"/api/jobs/{job_id}").json()
    assert after["remotePolicy"] == "hybrid"
    assert after["seniority"] == "staff"
