import json
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.scraper.browser_worker import (
    BrowserWorker,
    snapshot_from_html,
)
from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    CrawlLimits,
    Draft,
    PageUnderstanding,
)
from resume_tailor_harness.discovery.scraper.http_worker import HttpWorker
from resume_tailor_harness.discovery.scraper.replay import replay
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.security.outbound import PublicBytesResponse


ROOT = "https://careers.example.com"


def detail(number):
    value = {
        "@type": "JobPosting",
        "title": f"Engineer {number}",
        "hiringOrganization": {"name": "Example"},
        "description": "Build reliable services and support customers.",
    }
    return (
        '<html><body><script type="application/ld+json">'
        + json.dumps(value)
        + "</script></body></html>"
    )


class Gateway:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def document(self, url, budget, **kwargs):
        budget.check_deadline()
        self.calls.append(url)
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, int):
            return PublicBytesResponse(value, {}, b"", url)
        return PublicBytesResponse(200, {"etag": '"v1"'}, value.encode(), url)


def pages(control='<a class="next" href="?page=2">Next</a>'):
    return {
        ROOT + "/jobs": '<article><a href="/jobs/1">Engineer 1</a></article>' + control,
        ROOT
        + "/jobs?page=2": '<article><a href="/jobs/2">Engineer 2</a></article><button class="next" disabled>Next</button>',
        ROOT + "/jobs/1": detail(1),
        ROOT + "/jobs/2": detail(2),
    }


def draft():
    return Draft(
        source_id="board",
        url=ROOT + "/jobs",
        plan=BoardPlan(
            card_selector="article",
            link_selector="a",
            pagination="next",
            control_selector=".next",
        ),
    )


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    monkeypatch.setattr(
        BrowserWorker,
        "_start",
        lambda *_: pytest.fail("Browser launched in HTTP-only test"),
    )


def test_http_replay_paginates_relative_links_and_restores_listing():
    gateway = Gateway(pages())
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        result = replay(draft(), HttpWorker(gateway), ScrapeStore(session), None)
    assert result.terminal_reason == "complete"
    assert [item.facts.title for item in result.observations] == [
        "Engineer 1",
        "Engineer 2",
    ]
    assert all(item.accepted for item in result.observations)
    assert gateway.calls == [
        ROOT + "/jobs",
        ROOT + "/jobs/1",
        ROOT + "/jobs?page=2",
        ROOT + "/jobs/2",
    ]


@pytest.mark.parametrize(
    "control",
    [
        '<button class="next">More</button>',
        '<a class="next" href="javascript:loadMore()">More</a>',
    ],
)
def test_js_navigation_retains_partial_results_without_claiming_completion(control):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        result = replay(
            draft(), HttpWorker(Gateway(pages(control))), ScrapeStore(session), None
        )
    assert result.terminal_reason == "capability_unavailable"
    assert len(result.observations) == 1
    assert result.observations[0].accepted


@pytest.mark.parametrize("status,reason", [(403, "blocked"), (429, "throttled")])
def test_http_error_is_not_an_empty_board(status, reason):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        result = replay(
            draft(),
            HttpWorker(Gateway({ROOT + "/jobs": status})),
            ScrapeStore(session),
            None,
        )
    assert result.terminal_reason == reason


def test_browser_disabled_analyze_approve_refresh_uses_http(monkeypatch):
    import resume_tailor_harness.services.scrape_review as review

    gateway = Gateway(pages())
    monkeypatch.setattr(review, "build_gateway", lambda: gateway)
    monkeypatch.setattr(
        review, "get_settings", lambda: SimpleNamespace(public_browser_enabled=False)
    )
    monkeypatch.setattr(review, "validate_public_url", lambda _: None)
    monkeypatch.setattr(
        "resume_tailor_harness.tenancy.limits.enforce_active_budget", lambda: None
    )
    monkeypatch.setattr(review, "build_understand_agent", lambda: None)
    monkeypatch.setattr(review, "build_extract_agent", lambda: None)
    monkeypatch.setattr(
        review,
        "understand",
        lambda *_: PageUnderstanding(kind="listing", plan=draft().plan),
    )
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        proposal = review.analyze_url(
            session, ROOT + "/jobs", CrawlLimits(), allow_browser=False
        )
        assert proposal.validation.valid
        assert len(proposal.samples) == 2
        assert gateway.calls.count(ROOT + "/jobs") == 1  # reuse the initial response
        approval = review.approve_draft(
            session,
            proposal.id,
            proposal.revision,
            [item.job_key for item in proposal.samples],
        )
        report = review.pull_source(session, approval.source_id, refresh=True)
        assert report.terminal_reason == "complete"
        assert len(report.observations) == 2


def test_http_worker_preserves_conditional_cache_validators():
    from resume_tailor_harness.discovery.scraper.pacing import CrawlBudget

    worker = HttpWorker(Gateway({ROOT + "/jobs/1": detail(1)}))
    snapshot = worker.snapshot(ROOT + "/jobs/1", CrawlBudget(CrawlLimits()))
    assert snapshot.etag == '"v1"'
    assert snapshot.dynamic is False


def test_http_worker_initial_snapshot_still_checks_access_challenge():
    from resume_tailor_harness.discovery.scraper.pacing import CrawlBudget
    from resume_tailor_harness.security.browser_gateway import CrawlStopped

    snapshot = snapshot_from_html(ROOT + "/jobs", "<h1>Access denied</h1>")
    with pytest.raises(CrawlStopped):
        HttpWorker(Gateway({}), initial=snapshot).snapshot(
            snapshot.final_url, CrawlBudget(CrawlLimits())
        )


def test_single_posting_refresh_preserves_head_metadata_and_url_identity(monkeypatch):
    import resume_tailor_harness.services.scrape_review as review

    url = ROOT + "/jobs/1"
    html = (
        detail(1)
        .replace("<body>", "<head>")
        .replace(
            "</body>",
            "</head><body><h1>Engineer 1</h1><p>Build reliable services and support customers.</p></body>",
        )
    )
    gateway = Gateway({url: html})
    monkeypatch.setattr(review, "build_gateway", lambda: gateway)
    monkeypatch.setattr(
        review, "get_settings", lambda: SimpleNamespace(public_browser_enabled=False)
    )
    monkeypatch.setattr(review, "validate_public_url", lambda _: None)
    monkeypatch.setattr(
        "resume_tailor_harness.tenancy.limits.enforce_active_budget", lambda: None
    )
    monkeypatch.setattr(review, "build_understand_agent", lambda: None)
    monkeypatch.setattr(review, "build_extract_agent", lambda: None)
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        proposal = review.analyze_url(session, url, CrawlLimits(), allow_browser=False)
        assert proposal.validation.valid
        sample_key = proposal.samples[0].job_key
        approval = review.approve_draft(
            session, proposal.id, proposal.revision, [sample_key]
        )
        report = review.pull_source(session, approval.source_id, refresh=True)
        assert report.terminal_reason == "complete"
        assert len(report.observations) == 1
        assert report.observations[0].accepted
        assert report.observations[0].job_key == sample_key
