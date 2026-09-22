import httpx
import pytest
from sqlalchemy import create_engine, select

from resume_tailor_harness.security.source_cooldown import CooldownStore, SourceCooldown
from resume_tailor_harness.security.browser_gateway import (
    BrowserGateway,
    BrowserRequest,
    CrawlStopped,
)
from resume_tailor_harness.security.outbound import PublicBytesResponse
from resume_tailor_harness.discovery.scraper.pacing import HostScheduler, CrawlBudget
from resume_tailor_harness.discovery.scraper.contracts import CrawlLimits
from resume_tailor_harness.discovery.url_ingest import fetch


def test_cooldown_survives_restart_expires_and_does_not_store_urls(tmp_path):
    database = f"sqlite:///{tmp_path / 'state.db'}"
    now = [100.0]
    store = CooldownStore(create_engine(database), clock=lambda: now[0])
    url = "https://boards.example/acme/jobs?secret=private"
    store.block(url, "HTTP 403", seconds=60)
    restarted = CooldownStore(create_engine(database), clock=lambda: now[0])
    with pytest.raises(SourceCooldown, match="retry after"):
        restarted.check(url)
    restarted.check("https://boards.example/other/jobs")
    with store.engine.connect() as conn:
        serialized = str(conn.execute(select(store.table)).all())
    assert (
        "private" not in serialized
        and "acme" not in serialized
        and "example" not in serialized
    )
    now[0] = 161
    restarted.check(url)


def test_origin_throttle_affects_other_paths_but_not_other_hosts():
    store = CooldownStore(create_engine("sqlite://"))
    store.block("https://jobs.example/a", "HTTP 429", origin_only=True)
    with pytest.raises(SourceCooldown):
        store.check("https://jobs.example/b")
    store.check("https://employer.example/a")


def test_concurrent_shorter_failure_does_not_reduce_cooldown():
    store = CooldownStore(create_engine("sqlite://"), clock=lambda: 100)
    store.block("https://example.com/job", "robots policy", seconds=86400)
    store.block("https://example.com/job", "HTTP 403", seconds=60)
    with pytest.raises(SourceCooldown) as caught:
        store.check("https://example.com/job")
    assert caught.value.retry_at == 86500


def test_robots_denial_is_shared_between_gateways(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    calls = []

    def read(url, **kwargs):
        calls.append(url)
        return PublicBytesResponse(200, {}, b"User-agent: *\nDisallow: /private", url)

    for _ in range(2):
        gateway = BrowserGateway(HostScheduler(engine), fetcher=read)
        with pytest.raises(CrawlStopped, match="robots"):
            gateway.fetch(
                BrowserRequest("https://example.com/private"),
                CrawlBudget(CrawlLimits()),
            )
    assert calls == ["https://example.com/robots.txt"]


def test_http_denial_does_not_repeat_transport(monkeypatch):
    store = CooldownStore(create_engine("sqlite://"))
    monkeypatch.setattr(fetch, "default_store", lambda: store)
    calls = []

    def denied(url, **kwargs):
        calls.append(url)
        raise httpx.HTTPStatusError(
            "denied", request=httpx.Request("GET", url), response=httpx.Response(403)
        )

    monkeypatch.setattr(fetch, "fetch_public_text", denied)
    with pytest.raises(SourceCooldown, match="HTTP 403"):
        fetch.fetch_static("https://example.com/job")
    with pytest.raises(SourceCooldown):
        fetch.fetch_static("https://example.com/job")
    assert len(calls) == 1


def test_long_retry_after_records_cooldown_without_waiting():
    engine = create_engine("sqlite://")
    gateway = BrowserGateway(
        HostScheduler(engine),
        fetcher=lambda url, **kwargs: PublicBytesResponse(
            429, {"retry-after": "3600"}, b"", url
        ),
    )
    # Isolate retry policy from host pacing and robots acquisition.
    gateway._request = lambda *args: PublicBytesResponse(
        429, {"retry-after": "3600"}, b"", "https://example.com/jobs"
    )
    gateway.robots["https://example.com"] = (
        float("inf"),
        PublicBytesResponse(404, {}, b"", "https://example.com/robots.txt"),
    )
    with pytest.raises(CrawlStopped, match="HTTP 429"):
        gateway.fetch(
            BrowserRequest("https://example.com/jobs"), CrawlBudget(CrawlLimits())
        )
    with pytest.raises(SourceCooldown):
        gateway.cooldowns.check("https://example.com/other")


def test_queued_worker_rechecks_new_cooldown_and_releases_lease(monkeypatch):
    engine = create_engine("sqlite://")
    scheduler = HostScheduler(engine)
    gateway = BrowserGateway(
        scheduler,
        fetcher=lambda *args, **kwargs: pytest.fail(
            "Transport must not run after queued cooldown"
        ),
    )
    gateway.robots["https://example.com"] = (
        float("inf"),
        PublicBytesResponse(404, {}, b"", "https://example.com/robots.txt"),
    )
    acquire = gateway._acquire

    def queued(host, budget):
        lease = acquire(host, budget)
        gateway.cooldowns.block(
            "https://example.com/jobs", "HTTP 429", origin_only=True
        )
        return lease

    monkeypatch.setattr(gateway, "_acquire", queued)
    releases = []
    release = scheduler.release

    def record_release(lease, delay):
        releases.append(lease)
        release(lease, delay)

    monkeypatch.setattr(scheduler, "release", record_release)
    with pytest.raises(CrawlStopped, match="HTTP 429"):
        gateway.fetch(
            BrowserRequest("https://example.com/jobs"), CrawlBudget(CrawlLimits())
        )
    assert len(releases) == 1
