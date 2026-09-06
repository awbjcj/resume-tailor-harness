"""One controlled board through browser, review, approval, restart and re-pull."""

import os
from types import SimpleNamespace
import pytest
from sqlmodel import Session, col, select
from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    CrawlLimits,
    PageUnderstanding,
    JobFacts,
)
from resume_tailor_harness.security.outbound import PublicBytesResponse
from resume_tailor_harness.services import scrape_review as review
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.discovery.scraper.tables import ScrapeObservationRow
from resume_tailor_harness.tracking.tables import Job


class FixtureGateway:
    def document(self, url, budget):
        return self.fetch(type("Request", (), {"url": url})(), budget)

    def fetch(self, request, budget):
        if request.url.endswith("/jobs"):
            html = '<article><a href="/jobs/one">Engineer</a></article>'
        else:
            html = '<h1>Engineer</h1><div class="jd">Build reliable public services.</div><script type="application/ld+json">{"@type":"JobPosting","title":"Engineer","description":"Build reliable public services.","hiringOrganization":{"name":"Example"}}</script>'
        return PublicBytesResponse(
            200, {"content-type": "text/html"}, html.encode(), request.url
        )


class Learner:
    def run(self, *args):
        return SimpleNamespace(
            content=PageUnderstanding(
                kind="listing",
                plan=BoardPlan(
                    card_selector="article", link_selector="a", detail_selector=".jd"
                ),
            )
        )


@pytest.mark.skipif(
    os.environ.get("RUN_PUBLIC_BROWSER_TESTS") != "1", reason="Real Chromium opt-in"
)
def test_public_board_review_restart_and_repull(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "build_gateway", FixtureGateway)
    monkeypatch.setattr(review, "build_understand_agent", Learner)
    monkeypatch.setattr(review, "build_extract_agent", lambda: None)
    monkeypatch.setattr(review, "validate_public_url", lambda url: None)
    engine = make_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    init_db(engine)
    with Session(engine) as session:
        draft = review.analyze_url(session, "https://example.com/jobs", CrawlLimits())
        assert draft.validation.valid
        sample = draft.samples[0]
        corrected = JobFacts.model_validate(
            {
                **sample.facts.model_dump(),
                "title": "Reviewed engineer",
                "remote_policy": None,
            }
        )
        draft = review.patch_draft(
            session, draft.id, draft.revision, samples={sample.job_key: corrected}
        )
        result = review.approve_draft(
            session,
            draft.id,
            draft.revision,
            [sample.job_key] if sample.job_key is not None else [],
        )
        assert len(result.job_ids) == 1
    engine.dispose()
    engine = make_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    with Session(engine) as session:
        report = review.pull_source(session, draft.source_id)
        assert report.imported == 0
        assert report.duplicate == 1
        assert len(session.exec(select(Job)).all()) == 1
        latest = session.exec(
            select(ScrapeObservationRow).order_by(
                col(ScrapeObservationRow.observed_at).desc()
            )
        ).first()
        from resume_tailor_harness.discovery.scraper.contracts import Observation

        assert latest is not None
        effective = ScrapeStore(session).effective_facts(
            Observation.model_validate_json(latest.payload)
        )
        assert effective.title == "Reviewed engineer"
        assert effective.remote_policy is None
