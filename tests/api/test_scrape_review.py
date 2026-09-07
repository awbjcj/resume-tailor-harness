from fastapi.testclient import TestClient
from sqlmodel import Session

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.deps import get_session
from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.scraper.contracts import Draft
from resume_tailor_harness.discovery.scraper.store import ScrapeStore


def test_review_route_hides_missing_drafts_and_checks_revisions(tmp_path):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = ScrapeStore(session).save_draft(
            Draft(source_id="board", url="https://example.com/jobs")
        )
        session.commit()
    app = create_app(db_url="sqlite://", api_token="", data_dir=tmp_path)

    def session_dep():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_dep
    with TestClient(app) as client:
        assert client.get("/api/scrape/drafts/missing").status_code == 404
        response = client.get(f"/api/scrape/drafts/{draft.id}")
        assert response.status_code == 200
        assert response.json()["sourceId"] == "board"
        response = client.patch(
            f"/api/scrape/drafts/{draft.id}", json={"expectedRevision": 12}
        )
        assert response.status_code == 409
        response = client.post(
            f"/api/scrape/drafts/{draft.id}/approve",
            json={"expectedRevision": 0, "selectedKeys": []},
        )
        assert response.status_code == 422


def test_draft_corrections_do_not_change_job_overrides_before_approval(tmp_path):
    from resume_tailor_harness.discovery.scraper.contracts import Observation, JobFacts

    engine = make_engine("sqlite://")
    init_db(engine)
    observation = Observation(
        source_id="board",
        revision=0,
        job_key="one",
        facts=JobFacts(source_url="https://example.com/1", title="Engineer"),
    )
    with Session(engine) as session:
        draft = ScrapeStore(session).save_draft(
            Draft(
                source_id="board", url="https://example.com/jobs", samples=[observation]
            )
        )
        session.commit()
    app = create_app(db_url="sqlite://", api_token="", data_dir=tmp_path)

    def session_dep():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_dep
    with TestClient(app) as client:
        result = client.patch(
            f"/api/scrape/drafts/{draft.id}",
            json={
                "expectedRevision": 0,
                "samples": {
                    "one": {
                        "sourceUrl": "https://example.com/1",
                        "title": "Senior Engineer",
                    }
                },
            },
        )
        assert result.status_code == 200
    with Session(engine) as session:
        assert ScrapeStore(session).override_history("one") == []


def test_enhanced_url_entry_returns_board_review_result(tmp_path, monkeypatch):
    import time
    from types import SimpleNamespace
    from resume_tailor_harness.api.routers import runs
    from resume_tailor_harness.services import public_url_routing, scrape_review

    monkeypatch.setattr(
        scrape_review,
        "import_public_url",
        lambda *args, **kwargs: {
            "draftId": "review",
            "jobId": None,
            "duplicate": False,
        },
    )

    def legacy(*args, **kwargs):
        raise AssertionError("enhanced import must use structured public extraction")

    monkeypatch.setattr(runs, "add_job_from_url", legacy)
    monkeypatch.setattr(
        public_url_routing,
        "fetch_static",
        lambda url: SimpleNamespace(final_url=url),
    )
    app = create_app(db_url="sqlite://", api_token="", data_dir=tmp_path)
    with TestClient(app) as client:
        run = client.post(
            "/api/jobs/from-url",
            json={"url": "https://example.com/jobs", "publicExtraction": True},
        ).json()
        result = None
        for _ in range(100):
            result = client.get(f"/api/runs/{run['runId']}").json()
            if result["state"] in {"done", "error"}:
                break
            time.sleep(0.02)
        assert result is not None
        assert result["state"] == "done"
        assert result["result"]["draftId"] == "review"


def test_enhanced_url_entry_routes_redirected_ats_to_the_ats_reader(
    tmp_path, monkeypatch
):
    import time
    from types import SimpleNamespace

    from resume_tailor_harness.api.routers import runs
    from resume_tailor_harness.services import public_url_routing, scrape_review

    original_url = "https://jobs.example.test/redirect"
    monkeypatch.setattr(
        public_url_routing,
        "fetch_static",
        lambda url: SimpleNamespace(
            final_url="https://boards.greenhouse.io/acme/jobs/42"
        ),
    )

    def generic(*args, **kwargs):
        raise AssertionError("a redirected ATS URL must not use generic extraction")

    monkeypatch.setattr(scrape_review, "import_public_url", generic)
    monkeypatch.setattr(
        runs, "add_job_from_url", lambda *args, **kwargs: SimpleNamespace(id=42)
    )
    app = create_app(db_url="sqlite://", api_token="", data_dir=tmp_path)
    with TestClient(app) as client:
        run = client.post(
            "/api/jobs/from-url",
            json={"url": original_url, "publicExtraction": True},
        ).json()
        result = None
        for _ in range(100):
            result = client.get(f"/api/runs/{run['runId']}").json()
            if result["state"] in {"done", "error"}:
                break
            time.sleep(0.02)
        assert result is not None
        assert result["state"] == "done"
        assert result["result"] == {"jobId": 42, "duplicate": False}


def test_source_override_updates_the_canonical_job_and_invalidates_derived_state(
    tmp_path,
):
    from datetime import datetime

    from resume_tailor_harness.discovery.scraper.contracts import JobFacts, Observation
    from resume_tailor_harness.services.scrape_ingest import ingest_observation
    from resume_tailor_harness.tracking.tables import Job, JobStatus

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        observation = Observation(
            source_id="board",
            revision=1,
            job_key="one",
            accepted=True,
            facts=JobFacts(
                source_url="https://example.com/jobs/1",
                title="Engineer",
                company="Example",
                locations=["London"],
                posted_at="2026-06-01T12:00:00Z",
                jd_text="Original job description.",
            ),
        )
        job_id = ingest_observation(session, observation, ScrapeStore(session))
        assert job_id is not None
        job = session.get(Job, job_id)
        assert job is not None
        assert job.posted_at == datetime(2026, 6, 1, 12)
        job.status = JobStatus.extracted.value
        job.criteria_json = {"skills": ["Python"]}
        job.analysis_meta_json = {"industry": "software"}
        job.fit_score = 82
        job.fit_rationale = "Original rationale"
        job.reject_reason = "Original decision"
        job.reject_category = "filtered"
        job.industry_pending = True
        session.add(job)
        session.commit()

    app = create_app(db_url="sqlite://", api_token="", data_dir=tmp_path)

    def session_dep():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_dep
    with TestClient(app) as client:
        for field, value in (
            ("title", "Principal Engineer"),
            ("company", "Reviewed Example"),
            ("jd_text", "Corrected job description."),
        ):
            response = client.put(
                f"/api/jobs/{job_id}/source-overrides/{field}",
                json={"field": field, "value": value, "expectedRevision": 0},
            )
            assert response.status_code == 200

        response = client.delete(
            f"/api/jobs/{job_id}/source-overrides/title",
            params={"expected_revision": 1},
        )
        assert response.status_code == 200
        observations = client.get(
            f"/api/jobs/{job_id}/source-observations"
        ).json()
        assert observations[0]["facts"]["company"] == "Example"
        assert observations[0]["effectiveFacts"]["company"] == "Reviewed Example"

    with Session(engine) as session:
        job = session.get(Job, job_id)
        assert job is not None
        assert job.title == "Engineer"
        assert job.company == "Reviewed Example"
        assert job.jd_text == "Corrected job description."
        assert job.location == "London"
        assert job.status == JobStatus.raw.value
        assert job.criteria_json is None
        assert job.analysis_meta_json is None
        assert job.fit_score is None
        assert job.fit_rationale is None
        assert job.reject_reason is None
        assert job.reject_category is None
        assert job.industry_pending is False


def test_override_editor_targets_the_source_of_the_displayed_latest_observation():
    from resume_tailor_harness.api.routers.scrape import get_overrides
    from resume_tailor_harness.discovery.scraper.tables import ScrapeObservationRow
    from resume_tailor_harness.discovery.scraper.contracts import OverridePatch

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        session.add(
            ScrapeObservationRow(
                id="a",
                job_key="old-source",
                source_id="old",
                job_id=1,
                payload="{}",
                observed_at=1,
            )
        )
        session.add(
            ScrapeObservationRow(
                id="b",
                job_key="latest-source",
                source_id="new",
                job_id=1,
                payload="{}",
                observed_at=2,
            )
        )
        store = ScrapeStore(session)
        store.set_override(
            "latest-source",
            OverridePatch(field="title", value="Reviewed title", expected_revision=0),
        )
        assert get_overrides(1, session)[0].value == "Reviewed title"
