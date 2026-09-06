import pytest
import os

from resume_tailor_harness.discovery.scraper.browser_worker import (
    BrowserWorker,
    snapshot_from_html,
)
from resume_tailor_harness.discovery.scraper.contracts import BrowserAction, CrawlLimits
from resume_tailor_harness.discovery.scraper.pacing import BudgetExceeded, CrawlBudget
from resume_tailor_harness.security.outbound import PublicBytesResponse


def test_snapshot_preserves_structured_data_before_pruning():
    snapshot = snapshot_from_html(
        "https://example.com/jobs/1",
        '<script type="application/ld+json">{"@type":"JobPosting","title":"Engineer"}</script><h1>Engineer</h1>',
    )
    item = snapshot.json_ld[0]
    assert isinstance(item, dict)
    assert item["title"] == "Engineer"
    assert snapshot.visible_text == "Engineer"


class FixtureGateway:
    def fetch(self, request, budget):
        if request.url.endswith("/private"):
            raise ValueError("private destination blocked")
        html = '<html><body><h1>Engineer</h1><div id="jobs"></div><script>document.querySelector("#jobs").textContent="Dynamic job description";</script></body></html>'
        return PublicBytesResponse(
            200, {"content-type": "text/html"}, html.encode(), request.url
        )


@pytest.mark.skipif(
    os.environ.get("RUN_PUBLIC_BROWSER_TESTS") != "1",
    reason="Set RUN_PUBLIC_BROWSER_TESTS=1 with sandboxed Chromium installed",
)
def test_actual_browser_renders_dynamic_content_and_closes():
    budget = CrawlBudget(CrawlLimits(elapsed_seconds=30))
    with BrowserWorker(FixtureGateway()) as worker:
        snapshot = worker.snapshot("https://example.com/jobs/1", budget)
        assert "Dynamic job description" in snapshot.visible_text
    assert worker.alive is False


def test_cancelled_browser_does_not_navigate():
    budget = CrawlBudget(CrawlLimits(), cancelled=lambda: True)
    with BrowserWorker(FixtureGateway()) as worker:
        with pytest.raises(BudgetExceeded, match="cancelled"):
            worker.snapshot("https://example.com/jobs/1", budget)


def test_declared_actions_reject_arbitrary_execution():
    with pytest.raises(ValueError):
        BrowserAction.model_validate({"kind": "evaluate", "selector": "alert(1)"})


class DelayedGateway:
    def fetch(self, request, budget):
        html = '<html><body><h1>Engineer</h1><div id="jobs"></div><script>setTimeout(()=>document.querySelector("#jobs").textContent="Delayed complete description", 900)</script></body></html>'
        return PublicBytesResponse(
            200, {"content-type": "text/html"}, html.encode(), request.url
        )


@pytest.mark.skipif(
    os.environ.get("RUN_PUBLIC_BROWSER_TESTS") != "1",
    reason="Set RUN_PUBLIC_BROWSER_TESTS=1 with sandboxed Chromium installed",
)
def test_browser_waits_for_delayed_job_content():
    with BrowserWorker(DelayedGateway()) as worker:
        snapshot = worker.snapshot(
            "https://example.com/1", CrawlBudget(CrawlLimits(elapsed_seconds=30))
        )
        assert "Delayed complete description" in snapshot.visible_text


@pytest.mark.skipif(
    os.environ.get("RUN_PUBLIC_BROWSER_TESTS") != "1", reason="Real Chromium opt-in"
)
def test_real_browser_private_subrequest_is_blocked_by_production_gateway(tmp_path):
    import httpx
    from resume_tailor_harness.db import make_engine
    from resume_tailor_harness.discovery.scraper.pacing import HostScheduler
    from resume_tailor_harness.security.browser_gateway import BrowserGateway
    from resume_tailor_harness.security.outbound import fetch_public_bytes

    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b'<h1>Engineer</h1><script>fetch("http://127.0.0.1:8888/private").catch(()=>{});</script>',
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:

        def fetcher(url, **kwargs):
            return fetch_public_bytes(
                url, client=client, resolver=lambda _: {"8.8.8.8"}, **kwargs
            )

        gateway = BrowserGateway(
            HostScheduler(make_engine(f"sqlite:///{tmp_path / 'scheduler.db'}")),
            fetcher=fetcher,
        )
        with BrowserWorker(gateway) as worker:
            worker.snapshot(
                "https://example.com/jobs", CrawlBudget(CrawlLimits(elapsed_seconds=30))
            )
            assert worker.errors
        assert not any("127.0.0.1" in url for url in requests)


def test_disabled_public_browser_never_starts_a_child(monkeypatch):
    from resume_tailor_harness.config import get_settings
    from resume_tailor_harness.discovery.scraper.browser_worker import (
        BrowserUnavailable,
    )

    monkeypatch.setattr(get_settings(), "public_browser_enabled", False)
    with BrowserWorker(FixtureGateway()) as worker:
        with pytest.raises(BrowserUnavailable):
            worker.snapshot("https://example.com/jobs", CrawlBudget(CrawlLimits()))
        assert not worker.alive
