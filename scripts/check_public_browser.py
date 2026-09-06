"""Run as the deployment user to verify isolated Chromium; never accesses a live site."""

from resume_tailor_harness.discovery.scraper.browser_worker import BrowserWorker
from resume_tailor_harness.discovery.scraper.contracts import CrawlLimits
from resume_tailor_harness.discovery.scraper.pacing import CrawlBudget
from resume_tailor_harness.security.outbound import PublicBytesResponse


class FixtureGateway:
    def fetch(self, request, budget):
        return PublicBytesResponse(
            200,
            {"content-type": "text/html"},
            b"<h1>Public browser capability verified</h1>",
            request.url,
        )


if __name__ == "__main__":
    with BrowserWorker(FixtureGateway()) as worker:
        snapshot = worker.snapshot(
            "https://example.com/jobs", CrawlBudget(CrawlLimits(elapsed_seconds=30))
        )
        assert "Public browser capability verified" in snapshot.visible_text
    assert not worker.alive
    print("Sandboxed public browser and worker cleanup verified")
