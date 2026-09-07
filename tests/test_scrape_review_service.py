import pytest
from sqlmodel import Session, select

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    CrawlLimits,
    Draft,
    JobFacts,
    Observation,
    ValidationResult,
)
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.services.scrape_review import approve_draft
from resume_tailor_harness.tracking.tables import Job


def ready_draft(store):
    sample = Observation(
        source_id="board",
        revision=0,
        job_key="job-one",
        accepted=True,
        facts=JobFacts(
            source_url="https://example.com/jobs/1",
            title="Engineer",
            company="Example",
            jd_text="Build reliable services and support the engineering team.",
        ),
    )
    return store.save_draft(
        Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", detail_mode="inline", detail_selector=".jd"
            ),
            state="validated",
            validation=ValidationResult(valid=True),
            samples=[sample],
        )
    )


def test_approval_is_atomic_and_idempotent():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = ready_draft(ScrapeStore(session))
        session.commit()
        first = approve_draft(session, draft.id, draft.revision, ["job-one"])
        second = approve_draft(session, draft.id, draft.revision, ["job-one"])
        assert first == second
        assert len(session.exec(select(Job)).all()) == 1
        assert len(ScrapeStore(session).list_sources()) == 1


def test_static_posting_without_required_content_retries_in_browser(monkeypatch):
    from types import SimpleNamespace

    import resume_tailor_harness.services.scrape_review as review
    from resume_tailor_harness.discovery.scraper.browser_worker import (
        snapshot_from_html,
    )
    from resume_tailor_harness.discovery.scraper.contracts import PageUnderstanding
    from resume_tailor_harness.security.outbound import PublicBytesResponse

    static_html = "<main>Job posting shell</main>"
    rendered_html = "<h1>Engineer</h1><div class='jd'>Build reliable systems.</div>"

    class Gateway:
        def document(self, url, budget):
            return PublicBytesResponse(200, {}, static_html.encode(), url)

    class Worker:
        def __init__(self, gateway):
            self.gateway = gateway

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def snapshot(self, url, budget):
            return snapshot_from_html(url, rendered_html)

    plan = BoardPlan(
        card_selector="body", detail_mode="inline", detail_selector=".jd"
    )
    monkeypatch.setattr(review, "build_gateway", Gateway)
    monkeypatch.setattr(review, "BrowserWorker", Worker)
    monkeypatch.setattr(review, "build_understand_agent", lambda: object())
    monkeypatch.setattr(review, "build_extract_agent", lambda: object())
    monkeypatch.setattr(
        review,
        "get_settings",
        lambda: SimpleNamespace(public_browser_enabled=True),
    )
    monkeypatch.setattr(review, "validate_public_url", lambda _url: None)
    monkeypatch.setattr(
        "resume_tailor_harness.tenancy.limits.enforce_active_budget", lambda: None
    )
    monkeypatch.setattr(
        review,
        "understand",
        lambda snapshot, _agent: PageUnderstanding(kind="posting", plan=plan),
    )

    def extract(snapshot, source_id, revision, _agent):
        rendered = "Build reliable systems." in snapshot.visible_text
        return Observation(
            source_id=source_id,
            revision=revision,
            job_key="job-one",
            accepted=rendered,
            facts=JobFacts(
                source_url=snapshot.final_url,
                title="Engineer" if rendered else None,
                jd_text="Build reliable systems." if rendered else None,
            ),
        )

    monkeypatch.setattr(review, "extract_observation", extract)
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = review.analyze_url(
            session, "https://example.com/jobs/one", CrawlLimits()
        )

    assert draft.validation.valid
    assert draft.samples[0].facts.jd_text == "Build reliable systems."
    assert draft.navigation is not None
    assert draft.navigation.terminal_reason == "complete"


def test_failed_sample_ingest_rolls_back_source_approval(monkeypatch):
    import resume_tailor_harness.services.scrape_review as review

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = ready_draft(ScrapeStore(session))
        session.commit()

        def fail(*args, **kwargs):
            raise RuntimeError("simulated ingest failure")

        monkeypatch.setattr(review, "ingest_observation", fail)
        with pytest.raises(RuntimeError):
            approve_draft(session, draft.id, draft.revision, ["job-one"])
        assert ScrapeStore(session).list_sources() == []
        assert session.exec(select(Job)).all() == []


def test_approval_rejects_unseen_selected_job():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = ready_draft(ScrapeStore(session))
        session.commit()
        with pytest.raises(ValueError, match="sample"):
            approve_draft(session, draft.id, draft.revision, ["invented"])


def test_edit_source_reuses_saved_rules_without_mutating_approval():
    from resume_tailor_harness.services.scrape_review import edit_source

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = ready_draft(ScrapeStore(session))
        session.commit()
        approve_draft(session, draft.id, 0, [])
        edited = edit_source(session, "board")
        assert edited.id != draft.id
        assert edited.plan == draft.plan
        assert edited.base_revision == 1
        assert edited.state == "draft"
        assert not edited.validation.valid


@pytest.mark.parametrize("terminal", ["complete", "review_required", "blocked"])
def test_revalidation_keeps_user_corrections(monkeypatch, terminal):
    from resume_tailor_harness.services import scrape_review as review
    from resume_tailor_harness.discovery.scraper.contracts import PullReport

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = ready_draft(ScrapeStore(session))
        draft.corrections = {
            "job-one": {"title": "Corrected title", "remote_policy": None}
        }
        draft = ScrapeStore(session).save_draft(draft)
        session.commit()

        class Worker:
            def __init__(self, *args):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        monkeypatch.setattr(review, "BrowserWorker", Worker)
        monkeypatch.setattr(review, "build_gateway", lambda: None)
        monkeypatch.setattr(review, "build_extract_agent", lambda: None)
        monkeypatch.setattr(
            review,
            "replay",
            lambda *args, **kwargs: PullReport(
                observations=draft.samples, terminal_reason=terminal
            ),
        )
        result = review.revalidate_draft(session, draft.id, draft.revision)
        assert result.samples[0].facts.title == "Corrected title"
        assert result.samples[0].facts.remote_policy is None
        assert result.validation.valid == (terminal != "blocked")


def test_manual_correction_can_resolve_invalid_sample_field():
    from resume_tailor_harness.services.scrape_review import patch_draft
    from resume_tailor_harness.discovery.scraper.contracts import FieldIssue

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        draft = ready_draft(store)
        draft.samples[0].accepted = False
        draft.samples[0].issues = [FieldIssue(field="title", kind="conflict")]
        draft.validation.valid = False
        draft = store.save_draft(draft)
        session.commit()
        corrected = draft.samples[0].facts.model_copy(
            update={"title": "Reviewed engineer"}
        )
        result = patch_draft(
            session, draft.id, draft.revision, samples={"job-one": corrected}
        )
        assert result.samples[0].accepted
        assert result.validation.valid


def test_snapshot_picker_returns_observed_selectors_and_inert_text():
    from resume_tailor_harness.services.scrape_review import snapshot_elements
    from resume_tailor_harness.discovery.scraper.browser_worker import (
        snapshot_from_html,
    )
    from bs4 import BeautifulSoup

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        snapshot = snapshot_from_html(
            "https://example.com/1",
            '<article><h1 onclick="attack()">Engineer</h1><p>Build tools</p><script>attack()</script></article>',
        )
        ScrapeStore(session).save_snapshot(snapshot)
        elements = snapshot_elements(session, snapshot.id)
        assert elements
        assert all(
            BeautifulSoup(snapshot.html, "html.parser").select(item["selector"])
            for item in elements
        )
        assert all("attack()" not in item["text"] for item in elements)


def test_approval_rejects_a_job_override_changed_after_draft_creation():
    from resume_tailor_harness.discovery.scraper.contracts import OverridePatch
    from resume_tailor_harness.discovery.scraper.store import RevisionConflict

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        draft = ready_draft(store)
        draft.corrections = {"job-one": {"title": "Draft title"}}
        draft = store.save_draft(draft)
        store.set_override(
            "job-one",
            OverridePatch(field="title", value="Newer user edit", expected_revision=0),
        )
        session.commit()
        with pytest.raises(RevisionConflict):
            approve_draft(session, draft.id, draft.revision, ["job-one"])
        assert not store.list_sources()


def test_pull_source_keeps_earlier_imports_when_the_active_job_quota_is_reached(
    monkeypatch,
):
    from resume_tailor_harness.discovery.scraper.contracts import PullReport
    from resume_tailor_harness.services import discovery, scrape_review as review

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        draft = ready_draft(store)
        session.commit()
        approve_draft(session, draft.id, draft.revision, ["job-one"])

        first = Observation(
            source_id="board",
            revision=1,
            job_key="job-two",
            accepted=True,
            facts=JobFacts(
                source_url="https://example.com/jobs/2",
                title="Engineer Two",
                company="Example",
                jd_text="Build reliable services for a second team.",
            ),
        )
        second = Observation(
            source_id="board",
            revision=1,
            job_key="job-three",
            accepted=True,
            facts=JobFacts(
                source_url="https://example.com/jobs/3",
                title="Engineer Three",
                company="Example",
                jd_text="Build reliable services for a third team.",
            ),
        )

        class Worker:
            def __init__(self, *args):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(review, "BrowserWorker", Worker)
        monkeypatch.setattr(review, "build_gateway", lambda: None)
        monkeypatch.setattr(review, "build_extract_agent", lambda: None)
        monkeypatch.setattr(
            review,
            "replay",
            lambda *args, **kwargs: PullReport(observations=[first, second]),
        )
        monkeypatch.setattr(discovery, "active_limit", lambda *args, **kwargs: 2)

        report = review.pull_source(session, draft.source_id)

        assert report.imported == 1
        assert report.terminal_reason == "partial_limit"
        assert report.messages == ["active job limit reached (2)"]
        assert {job.title for job in session.exec(select(Job)).all()} == {
            "Engineer",
            "Engineer Two",
        }
