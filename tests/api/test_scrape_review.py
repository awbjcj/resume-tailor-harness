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
    from resume_tailor_harness.api.routers import runs
    from resume_tailor_harness.services import scrape_review

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
    app = create_app(db_url="sqlite://", api_token="", data_dir=tmp_path)
    with TestClient(app) as client:
        run = client.post(
            "/api/jobs/from-url",
            json={"url": "https://example.com/jobs", "publicExtraction": True},
        ).json()
        for _ in range(100):
            result = client.get(f"/api/runs/{run['runId']}").json()
            if result["state"] in {"done", "error"}:
                break
            time.sleep(0.02)
        assert result["state"] == "done"
        assert result["result"]["draftId"] == "review"


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
