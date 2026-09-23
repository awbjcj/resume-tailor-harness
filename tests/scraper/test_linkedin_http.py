from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from resume_tailor_harness.discovery.scraper.linkedin_http import LinkedInHttpScraper
from resume_tailor_harness.discovery.search_config import SearchConfig
from resume_tailor_harness.security.outbound import PublicBytesResponse

FIXTURES = Path(__file__).parents[1] / "fixtures" / "linkedin"


class Gateway:
    def __init__(self, *, fail_detail=False, repeated=False, challenge=False):
        self.calls = []
        self.fail_detail = fail_detail
        self.repeated = repeated
        self.challenge = challenge

    def document(self, url, budget):
        self.calls.append(url)
        if "seeMoreJobPostings" in url:
            offset = parse_qs(urlsplit(url).query)["start"][0]
            html = (
                (FIXTURES / "search.html").read_text(encoding="utf-8")
                if offset == "0" or self.repeated
                else ""
            )
            html = html.replace("</div>", '<time datetime="2026-09-20"></time></div>')
            if self.challenge:
                html = "<h1>Verify you are human</h1>"
        elif self.fail_detail and "3700000001" in url:
            return PublicBytesResponse(404, {}, b"", url)
        else:
            html = '<h1 class="top-card-layout__title">Backend Engineer</h1>' + (
                FIXTURES / "job.html"
            ).read_text(encoding="utf-8")
        return PublicBytesResponse(200, {}, html.encode(), url)


def test_http_search_fetches_full_details_and_paginates():
    gateway = Gateway()
    result = LinkedInHttpScraper(gateway=gateway).fetch(SearchConfig())
    assert len(result.jobs) == 2
    assert all("5+ years of Python" in job.jd_text for job in result.jobs)
    assert result.failures == {}
    assert "start=2" in gateway.calls[-1]
    assert all(job.posted_at for job in result.jobs)


def test_limit_counts_successful_details_not_failed_cards():
    gateway = Gateway(fail_detail=True)
    result = LinkedInHttpScraper(gateway=gateway).fetch(SearchConfig(), limit=1)
    assert len(result.jobs) == 1
    assert "3700000002" in result.jobs[0].url
    assert len(result.failures) == 1


def test_known_job_is_skipped_before_detail_request():
    gateway = Gateway()
    result = LinkedInHttpScraper(gateway=gateway).fetch(
        SearchConfig(), skip_seen=lambda job: "3700000001" in job.url
    )
    assert len(result.jobs) == 1
    assert not any("3700000001" in url for url in gateway.calls)


@pytest.mark.parametrize("options", [{"repeated": True}, {"challenge": True}])
def test_repeats_and_challenges_are_reported(options):
    result = LinkedInHttpScraper(gateway=Gateway(**options)).fetch(SearchConfig())
    assert result.failures
    if options.get("repeated"):
        assert len(result.jobs) == 2
    else:
        assert not result.jobs


def test_disabled_browser_registry_builds_http_connector():
    from resume_tailor_harness.config import Settings
    from resume_tailor_harness.discovery.connectors.config import ConnectorsConfig
    from resume_tailor_harness.discovery.connectors.registry import spec_for

    config = ConnectorsConfig()
    config.linkedin.limit = 7
    connector = spec_for("linkedin").build(
        [], config, Settings.model_construct(browser_enabled=False)
    )
    assert isinstance(connector, LinkedInHttpScraper)
    assert connector.configured_limit == 7


def test_blocked_detail_uses_card_identity_for_employer_recovery(monkeypatch):
    from resume_tailor_harness.discovery.scraper import linkedin_http
    from resume_tailor_harness.discovery.connectors.base import RawJob
    from resume_tailor_harness.security.browser_gateway import CrawlStopped

    class BlockedDetails(Gateway):
        def document(self, url, budget):
            if "seeMoreJobPostings" not in url:
                raise CrawlStopped("blocked", "HTTP 403")
            return super().document(url, budget)

    calls = []

    def recover(url, hints):
        calls.append(hints)
        return RawJob(
            source="url",
            url="https://jobs.lever.co/acme/1",
            company=hints.company,
            title=hints.title,
            location=hints.location,
            jd_text="Full employer posting",
        )

    monkeypatch.setattr(linkedin_http, "recover_employer_posting", recover)
    result = LinkedInHttpScraper(gateway=BlockedDetails()).fetch(
        SearchConfig(), limit=1
    )
    assert len(result.jobs) == 1 and not result.failures
    assert result.jobs[0].url == "https://jobs.lever.co/acme/1"
    assert calls[0].company and calls[0].title
