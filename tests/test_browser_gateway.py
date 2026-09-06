import httpx
import pytest

from resume_tailor_harness.security.outbound import fetch_public_bytes


def test_browser_gateway_blocks_robots_disallowed_pages(tmp_path):
    from sqlalchemy import create_engine
    from resume_tailor_harness.discovery.scraper.contracts import CrawlLimits
    from resume_tailor_harness.discovery.scraper.pacing import (
        CrawlBudget,
        HostScheduler,
    )
    from resume_tailor_harness.security.browser_gateway import (
        BrowserGateway,
        BrowserRequest,
    )
    from resume_tailor_harness.security.outbound import PublicBytesResponse

    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return PublicBytesResponse(200, {}, b"User-agent: *\nDisallow: /private\n", url)

    gateway = BrowserGateway(
        HostScheduler(create_engine(f"sqlite:///{tmp_path / 's.db'}")), fetcher=fetch
    )
    with pytest.raises(ValueError, match="robots"):
        gateway.fetch(
            BrowserRequest("https://example.com/private"), CrawlBudget(CrawlLimits())
        )
    assert calls == ["https://example.com/robots.txt"]


def test_gateway_pins_public_address_and_preserves_json():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200, headers={"content-type": "application/json"}, content=b'{"jobs":[]}'
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = fetch_public_bytes(
            "https://jobs.example/api", client=client, resolver=lambda host: {"8.8.8.8"}
        )
    assert response.body == b'{"jobs":[]}'
    assert seen[0].url.host == "8.8.8.8"
    assert seen[0].headers["host"] == "jobs.example"
    assert seen[0].extensions["sni_hostname"] == "jobs.example"


def test_private_browser_request_never_reaches_transport():
    seen = []
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: seen.append(r))
    ) as client:
        with pytest.raises(ValueError, match="public"):
            fetch_public_bytes("http://169.254.169.254/", client=client)
    assert seen == []


def test_redirect_is_returned_for_per_hop_browser_policy():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"location": "http://127.0.0.1/"})
        )
    ) as client:
        response = fetch_public_bytes(
            "https://jobs.example/", client=client, resolver=lambda host: {"8.8.8.8"}
        )
    assert response.status == 302
    assert response.headers["location"] == "http://127.0.0.1/"


def test_page_bytes_limit_enforced_before_returning():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, headers={"content-type": "text/html"}, content=b"12345"
            )
        )
    ) as client:
        with pytest.raises(ValueError, match="large"):
            fetch_public_bytes(
                "https://jobs.example/",
                client=client,
                resolver=lambda host: {"8.8.8.8"},
                max_bytes=4,
            )


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_unclassified_mutations_rejected(method):
    with pytest.raises(ValueError, match="read-only"):
        fetch_public_bytes("https://jobs.example/", method=method)


def test_only_bounded_json_job_search_posts_are_classified_read_only():
    from resume_tailor_harness.security.browser_gateway import (
        BrowserRequest,
        is_read_only_search,
    )

    assert is_read_only_search(
        BrowserRequest(
            "https://example.com/api/jobs/search",
            "POST",
            {"content-type": "application/json"},
            b'{"query":"engineer","page":1}',
            "fetch",
        )
    )
    assert not is_read_only_search(
        BrowserRequest(
            "https://example.com/api/jobs",
            "POST",
            {"content-type": "application/json"},
            b'{"title":"Create a job"}',
            "fetch",
        )
    )
    assert not is_read_only_search(
        BrowserRequest(
            "https://example.com/graphql",
            "POST",
            {"content-type": "application/json"},
            b'{"query":"mutation { deleteJob(id: 1) }"}',
            "fetch",
        )
    )
    assert not is_read_only_search(
        BrowserRequest(
            "https://example.com/apply",
            "POST",
            {"content-type": "application/json"},
            b'{"query":"engineer"}',
            "fetch",
        )
    )


def test_assets_share_one_paced_page_acquisition():
    from resume_tailor_harness.security.browser_gateway import (
        BrowserGateway,
        BrowserRequest,
    )
    from resume_tailor_harness.security.outbound import PublicBytesResponse
    from resume_tailor_harness.discovery.scraper.pacing import CrawlBudget, HostLease
    from resume_tailor_harness.discovery.scraper.contracts import CrawlLimits

    class Scheduler:
        acquisitions = 0
        releases = 0

        def acquire(self, host, owner, deadline):
            self.acquisitions += 1
            return HostLease(host, owner, 1, deadline)

        def renew(self, lease):
            return True

        def release(self, lease, delay):
            assert delay >= 3
            self.releases += 1

    scheduler = Scheduler()
    gateway = BrowserGateway(
        scheduler,
        fetcher=lambda url, **kw: PublicBytesResponse(
            404 if url.endswith("robots.txt") else 200, {}, b"", url
        ),
    )
    budget = CrawlBudget(CrawlLimits())
    gateway.begin_page("https://example.com/jobs", budget)
    gateway.fetch(BrowserRequest("https://example.com/jobs"), budget)
    gateway.fetch(
        BrowserRequest("https://example.com/app.js", resource_type="script"), budget
    )
    gateway.fetch(
        BrowserRequest("https://example.com/app.css", resource_type="stylesheet"),
        budget,
    )
    gateway.end_page()
    assert scheduler.acquisitions == 1
    assert scheduler.releases == 1
