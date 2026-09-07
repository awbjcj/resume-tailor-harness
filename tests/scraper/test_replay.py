import pytest
from sqlmodel import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.scraper.browser_worker import snapshot_from_html
from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    CrawlLimits,
    Draft,
    JobFacts,
    Observation,
    ValidationResult,
)
from resume_tailor_harness.discovery.scraper.replay import replay
from resume_tailor_harness.discovery.scraper.store import ScrapeStore


class FixtureWorker:
    errors = []
    gateway: object | None = None

    def __init__(self):
        self.details = 0

    def snapshot(self, url, budget):
        if url.endswith("/jobs"):
            return snapshot_from_html(
                url,
                '<article><a href="/jobs/1">One</a></article><article><a href="/jobs/2">Two</a></article><button class="next">Next</button>',
            )
        self.details += 1
        return snapshot_from_html(
            url,
            '<h1>Engineer</h1><div class="jd">Build reliable systems.</div><script type="application/ld+json">{"@type":"JobPosting","title":"Engineer","description":"Build reliable systems."}</script>',
        )

    def act(self, action, budget):
        if action.url:
            return self.snapshot(action.url, budget)
        return self.snapshot("https://example.com/jobs", budget)


def test_replay_stops_detail_budget_with_partial_outcome():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
            limits=CrawlLimits(detail_pages=1),
        )
        worker = FixtureWorker()
        report = replay(draft, worker, ScrapeStore(session), None)
        assert report.terminal_reason == "partial_limit"
        assert report.inspected == 1
        assert worker.details == 1


@pytest.mark.parametrize("pagination", ["next", "numbered", "load_more", "infinite"])
def test_repeated_page_stops_without_claiming_complete_coverage(pagination):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article",
                link_selector="a",
                detail_selector=".jd",
                pagination=pagination,
                control_selector=".next",
            ),
        )
        report = replay(draft, FixtureWorker(), ScrapeStore(session), None)
        assert report.terminal_reason == "review_required"
        assert report.inspected == 2


def test_missing_saved_pagination_control_requires_review():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article",
                link_selector="a",
                detail_selector=".jd",
                pagination="next",
                control_selector=".missing-next",
            ),
        )
        report = replay(draft, FixtureWorker(), ScrapeStore(session), None)
        assert report.terminal_reason == "review_required"
        assert report.messages == [
            "Saved pagination control no longer matches the page"
        ]


def test_preview_samples_are_bounded_and_persisted():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        report = replay(
            draft, FixtureWorker(), ScrapeStore(session), None, preview=True
        )
        assert len(report.observations) == 2
        assert report.observations[0].accepted


def test_preview_prefers_distinct_visible_card_layouts(monkeypatch):
    import importlib

    module = importlib.import_module("resume_tailor_harness.discovery.scraper.replay")
    inspected = []

    class LayoutWorker(FixtureWorker):
        def snapshot(self, url, budget):
            if url.endswith("/jobs"):
                return snapshot_from_html(
                    url,
                    '<article class="standard"><a href="/jobs/1">One</a></article>'
                    '<article class="standard"><a href="/jobs/2">Two</a></article>'
                    '<article class="featured"><header>Featured</header><a href="/jobs/3">Three</a></article>'
                    '<article class="standard"><a href="/jobs/4">Four</a></article>',
                )
            inspected.append(url)
            return super().snapshot(url, budget)

    monkeypatch.setattr(
        module,
        "extract_observation",
        lambda detail, source_id, revision, agent, field_rules: Observation(
            source_id=source_id,
            revision=revision,
            job_key=detail.final_url,
            accepted=True,
            facts=JobFacts(
                source_url=detail.final_url,
                title="Engineer",
                jd_text="Build reliable systems.",
            ),
        ),
    )
    monkeypatch.setattr(
        module, "validate_evidence", lambda *args: ValidationResult(valid=True)
    )
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        report = replay(
            draft, LayoutWorker(), ScrapeStore(session), None, preview=True
        )

    assert inspected == [
        "https://example.com/jobs/1",
        "https://example.com/jobs/3",
        "https://example.com/jobs/2",
    ]
    assert report.discovered == 4
    assert report.inspected == 3
    assert report.terminal_reason == "partial_limit"


def test_repull_reuses_fresh_detail_snapshots_until_explicit_refresh():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        store = ScrapeStore(session)
        first = FixtureWorker()
        replay(draft, first, store, None)
        session.commit()
        second = FixtureWorker()
        replay(draft, second, store, None)
        assert second.details == 0
        replay(draft, second, store, None, refresh=True)
        assert second.details == 2


def test_saved_location_rule_keeps_grounded_evidence():
    from resume_tailor_harness.discovery.scraper.contracts import FieldRule

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article",
                link_selector="a",
                detail_selector=".jd",
                field_rules=[FieldRule(field="locations", selector="h1")],
            ),
        )
        report = replay(draft, FixtureWorker(), ScrapeStore(session), None)
        item = report.observations[0]
        assert item.facts.locations == ["Engineer"]
        assert any(e.field == "locations" and e.selector == "h1" for e in item.evidence)


def test_unchanged_snapshot_reuses_verified_extraction(monkeypatch):
    import importlib

    module = importlib.import_module("resume_tailor_harness.discovery.scraper.replay")
    calls = []
    original = module.extract_observation

    def extract(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(module, "extract_observation", extract)
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        store = ScrapeStore(session)
        replay(draft, FixtureWorker(), store, None)
        replay(draft, FixtureWorker(), store, None)
        assert len(calls) == 2


def test_expired_static_detail_is_conditionally_revalidated_without_browser():
    from resume_tailor_harness.discovery.scraper.tables import ScrapeCacheRow
    from resume_tailor_harness.security.outbound import PublicBytesResponse

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        store = ScrapeStore(session)
        for number in (1, 2):
            url = f"https://example.com/jobs/{number}"
            snapshot = FixtureWorker().snapshot(url, None)
            snapshot.etag = '"v1"'
            snapshot.dynamic = False
            key = f"board:detail:{url}"
            store.cache_snapshot(key, snapshot)
            row = session.get(ScrapeCacheRow, key)
            assert row is not None
            row.expires_at = 0
            session.add(row)

        class Gateway:
            def document(self, url, budget, headers=None):
                assert headers == {"if-none-match": '"v1"'}
                return PublicBytesResponse(304, {}, b"", url)

        worker = FixtureWorker()
        worker.gateway = Gateway()
        report = replay(draft, worker, store, None)
        assert report.inspected == 2
        assert worker.details == 0


def test_unavailable_browser_is_not_reported_as_empty():
    from resume_tailor_harness.discovery.scraper.browser_worker import (
        BrowserUnavailable,
    )

    class Worker:
        def snapshot(self, *args):
            raise BrowserUnavailable("Sandbox is unavailable")

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        result = replay(draft, Worker(), ScrapeStore(session), None)
        assert result.terminal_reason == "capability_unavailable"


@pytest.mark.parametrize("reason", ["blocked", "throttled"])
def test_acquisition_stop_keeps_its_terminal_reason(reason):
    from resume_tailor_harness.security.browser_gateway import CrawlStopped

    class Worker:
        def snapshot(self, *args):
            raise CrawlStopped(reason, "Website asked the crawler to stop")

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        result = replay(draft, Worker(), ScrapeStore(session), None)
        assert result.terminal_reason == reason


def test_replay_tracks_learned_inline_identity_on_a_repeated_listing(monkeypatch):
    import importlib

    module = importlib.import_module("resume_tailor_harness.discovery.scraper.replay")

    class Worker:
        errors = []

        def __init__(self):
            self.next_calls = 0

        def snapshot(self, url, budget):
            return snapshot_from_html(
                url,
                "<article><h1>Engineer</h1><span>role-1</span>"
                "<div class='jd'>Build reliable services.</div></article>"
                "<button class='next'>Next</button>",
            )

        def act(self, action, budget):
            assert action.kind == "next"
            self.next_calls += 1
            return self.snapshot("https://example.com/jobs", budget)

    def extract(detail, source_id, revision, agent, field_rules):
        return Observation(
            source_id=source_id,
            revision=revision,
            accepted=True,
            facts=JobFacts(
                source_url=detail.final_url,
                posting_id="role-1",
                title="Engineer",
                jd_text="Build reliable services.",
            ),
        )

    monkeypatch.setattr(module, "extract_observation", extract)
    monkeypatch.setattr(
        module, "validate_evidence", lambda *args: ValidationResult(valid=True)
    )
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article",
                detail_mode="inline",
                detail_selector=".jd",
                pagination="next",
                control_selector=".next",
            ),
        )
        worker = Worker()
        report = replay(draft, worker, ScrapeStore(session), None)

    assert report.inspected == 1
    assert report.discovered == 1
    assert len(report.observations) == 1
    assert report.observations[0].job_key is not None
    assert worker.next_calls == 1
    assert report.terminal_reason == "review_required"


def test_replay_restores_the_listing_after_detail_navigation_fails():
    class Worker:
        errors = []

        def __init__(self):
            self.close_calls = 0

        def snapshot(self, url, budget):
            return snapshot_from_html(
                url,
                '<article><a href="/jobs/1">One</a></article>',
            )

        def act(self, action, budget):
            if action.kind == "open_detail":
                raise RuntimeError("detail navigation failed")
            assert action.kind == "close_detail"
            self.close_calls += 1
            return self.snapshot("https://example.com/jobs", budget)

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="board",
            url="https://example.com/jobs",
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        worker = Worker()
        report = replay(draft, worker, ScrapeStore(session), None)

    assert worker.close_calls == 1
    assert report.failed == 1
    assert report.messages == ["detail navigation failed"]
    assert report.terminal_reason == "review_required"
