import pytest

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
    assert snapshot.json_ld[0]["title"] == "Engineer"
    assert snapshot.visible_text == "Engineer"


class FixtureGateway:
    def fetch(self, request, budget):
        if request.url.endswith("/private"):
            raise ValueError("private destination blocked")
        html = '<html><body><h1>Engineer</h1><div id="jobs"></div><script>document.querySelector("#jobs").textContent="Dynamic job description";</script></body></html>'
        return PublicBytesResponse(
            200, {"content-type": "text/html"}, html.encode(), request.url
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
        BrowserAction(kind="evaluate", selector="alert(1)")
