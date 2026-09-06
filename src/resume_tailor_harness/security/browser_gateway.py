"""Browser traffic broker. No browser request uses ambient credentials."""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from resume_tailor_harness.discovery.scraper.pacing import (
    CrawlBudget,
    HostScheduler,
    retry_delay,
    robots_decision,
)
from resume_tailor_harness.security.outbound import (
    PublicBytesResponse,
    fetch_public_bytes,
)


@dataclass(frozen=True)
class BrowserRequest:
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    resource_type: str = "document"


BrowserResponse = PublicBytesResponse


class BrowserGateway:
    def __init__(
        self,
        scheduler: HostScheduler,
        *,
        fetcher: Callable[..., PublicBytesResponse] = fetch_public_bytes,
    ):
        self.scheduler = scheduler
        self.fetcher = fetcher
        self.owner = uuid4().hex
        self.robots: dict[str, tuple[float, PublicBytesResponse]] = {}

    def _wait(self, seconds: float, budget: CrawlBudget) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            budget.check_deadline()
            time.sleep(min(0.1, end - time.monotonic()))

    def _request(
        self, request: BrowserRequest, budget: CrawlBudget, delay: float = 3
    ) -> BrowserResponse:
        host = urlsplit(request.url).hostname
        if not host:
            raise ValueError("a public HTTP URL is required")
        while True:
            budget.check_deadline()
            lease = self.scheduler.acquire(
                host, self.owner, time.time() + max(0, budget.deadline - budget.clock())
            )
            if lease:
                break
            self._wait(0.1, budget)
        try:
            budget.charge_request()
            response = self.fetcher(
                request.url,
                method=request.method,
                headers=request.headers,
                max_bytes=20 * 1024 * 1024 - budget.bytes,
                timeout=min(20, max(0.1, budget.deadline - budget.clock())),
            )
            budget.charge_bytes(len(response.body))
            return response
        finally:
            self.scheduler.release(lease, delay + random.uniform(0, 2))

    def fetch(self, request: BrowserRequest, budget: CrawlBudget) -> BrowserResponse:
        if request.method not in {"GET", "HEAD"} or request.body:
            raise ValueError("unclassified non-read-only request is blocked")
        parsed = urlsplit(request.url)
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        cached = self.robots.get(origin)
        if cached is None or cached[0] < time.time():
            robots = self._request(BrowserRequest(origin + "/robots.txt"), budget)
            self.robots[origin] = (time.time() + 86400, robots)
        else:
            robots = cached[1]
        decision = robots_decision(
            request.url, robots.status, robots.body.decode("utf-8", errors="replace")
        )
        if not decision.allowed:
            raise ValueError(decision.reason)
        for attempt in range(3):
            response = self._request(request, budget, decision.delay_seconds)
            if response.status not in {429, 503}:
                return response
            if attempt == 2:
                raise ValueError("website throttled the crawl; retry later")
            self._wait(
                retry_delay(response.headers.get("retry-after"), attempt), budget
            )
        raise RuntimeError("crawl retries exhausted")
