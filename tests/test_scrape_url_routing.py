from sqlmodel import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.scraper.contracts import (
    Draft,
    JobFacts,
    Observation,
)
from resume_tailor_harness.services.scrape_review import import_public_url


def test_board_url_routes_to_review_without_combining_jobs(monkeypatch):
    import resume_tailor_harness.services.scrape_review as review

    draft = Draft(source_id="board", url="https://example.com/jobs")
    monkeypatch.setattr(review, "analyze_url", lambda *args, **kwargs: draft)
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        result = import_public_url(session, draft.url)
        assert result["draftId"] == draft.id
        assert result["jobId"] is None


def test_valid_single_posting_imports_with_evidence(monkeypatch):
    import resume_tailor_harness.services.scrape_review as review

    sample = Observation(
        source_id="board",
        revision=0,
        job_key="one",
        accepted=True,
        facts=JobFacts(
            source_url="https://example.com/jobs/1",
            title="Engineer",
            jd_text="Build reliable services for customers",
        ),
    )
    draft = Draft(
        source_id="board",
        url=sample.facts.source_url,
        page_kind="posting",
        samples=[sample],
    )
    monkeypatch.setattr(review, "analyze_url", lambda *args, **kwargs: draft)
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        result = import_public_url(session, draft.url)
        assert result["jobId"] is not None
