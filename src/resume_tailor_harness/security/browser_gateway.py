"""Browser traffic broker. No browser request uses ambient credentials."""

import random
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit
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


class CrawlStopped(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.code = "CRAWL_" + reason.upper()


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
        self.response_headers: dict[str, dict[str, str]] = {}
        self.prefetched: dict[str, BrowserResponse] = {}
        self._in_page = False
        self._page_leases = {}
        self._page_delays = {}
        self._renew_at = 0.0

    def _wait(self, seconds: float, budget: CrawlBudget) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            budget.check_deadline()
            self.renew_page()
            time.sleep(min(0.1, end - time.monotonic()))

    def _request(
        self, request: BrowserRequest, budget: CrawlBudget, delay: float = 3
    ) -> BrowserResponse:
        host = urlsplit(request.url).hostname
        if not host:
            raise ValueError("a public HTTP URL is required")
        lease = self._page_leases.get(host) if self._in_page else None
        if lease is None:
            lease = self._acquire(host, budget)
            if self._in_page:
                self._page_leases[host] = lease
        if self._in_page:
            self._page_delays[host] = max(delay, self._page_delays.get(host, 3))
        try:
            budget.charge_request()
            extra = (
                {"body": request.body, "read_only_search": True}
                if request.method == "POST"
                else {}
            )
            response = self.fetcher(
                request.url,
                **extra,
                method=request.method,
                headers=request.headers,
                max_bytes=20 * 1024 * 1024 - budget.bytes,
                timeout=min(20, max(0.1, budget.deadline - budget.clock())),
            )
            budget.charge_bytes(len(response.body))
            if request.resource_type == "document":
                self.response_headers[request.url] = response.headers
            return response
        finally:
            if not self._in_page:
                self.scheduler.release(lease, delay + random.uniform(0, 2))

    def _acquire(self, host: str, budget: CrawlBudget):
        while True:
            budget.check_deadline()
            lease = self.scheduler.acquire(
                host, self.owner, time.time() + max(0, budget.deadline - budget.clock())
            )
            if lease:
                return lease
            self._wait(0.1, budget)

    def begin_page(self, url: str, budget: CrawlBudget) -> None:
        self._in_page = True
        self._renew_at = time.monotonic() + 20
        host = urlsplit(url).hostname
        if host:
            self._page_leases[host] = self._acquire(host, budget)
            self._page_delays[host] = 3

    def renew_page(self) -> None:
        if self._in_page and time.monotonic() >= self._renew_at:
            for lease in self._page_leases.values():
                if not self.scheduler.renew(lease):
                    raise RuntimeError("Page acquisition lease expired")
            self._renew_at = time.monotonic() + 20

    def end_page(self) -> None:
        for host, lease in self._page_leases.items():
            self.scheduler.release(
                lease, self._page_delays.get(host, 3) + random.uniform(0, 2)
            )
        self._page_leases.clear()
        self._page_delays.clear()
        self._in_page = False

    def fetch(self, request: BrowserRequest, budget: CrawlBudget) -> BrowserResponse:
        budget.check_deadline()
        if request.method == "GET" and request.url in self.prefetched:
            return self.prefetched.pop(request.url)
        if request.method not in {"GET", "HEAD"} or request.body:
            if not is_read_only_search(request):
                raise ValueError("unclassified non-read-only request is blocked")
        parsed = urlsplit(request.url)
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        cached = self.robots.get(origin)
        if cached is None or cached[0] < time.time():
            robots = self._request(BrowserRequest(origin + "/robots.txt"), budget)
            if robots.status in {200, 404, 410}:
                self.robots[origin] = (time.time() + 86400, robots)
        else:
            robots = cached[1]
        decision = robots_decision(
            request.url, robots.status, robots.body.decode("utf-8", errors="replace")
        )
        if not decision.allowed:
            raise CrawlStopped("blocked", decision.reason)
        for attempt in range(3):
            response = self._request(request, budget, decision.delay_seconds)
            if response.status in {401, 403}:
                raise CrawlStopped(
                    "blocked", f"Website denied access: HTTP {response.status}"
                )
            if response.status not in {429, 503}:
                return response
            if attempt == 2:
                raise CrawlStopped(
                    "throttled", "website throttled the crawl; retry later"
                )
            self._wait(
                retry_delay(response.headers.get("retry-after"), attempt), budget
            )
        raise RuntimeError("crawl retries exhausted")

    def document(
        self, url: str, budget: CrawlBudget, headers: dict[str, str] | None = None
    ) -> BrowserResponse:
        for _ in range(6):
            response = self.fetch(BrowserRequest(url, headers=headers or {}), budget)
            if response.status not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if not location:
                raise ValueError("Redirect is missing its destination")
            url = urljoin(url, location)
        raise ValueError("Too many public-page redirects")


def is_read_only_search(request: BrowserRequest) -> bool:
    """Recognize bounded public job-search reads, never forms or generic API writes.

    Only a browser-observed JSON search endpoint is supported. GraphQL and
    unclassified POST APIs stay blocked until their semantics can be verified.
    """
    if request.method != "POST" or request.resource_type not in {"fetch", "xhr"}:
        return False
    if not request.body or len(request.body) > 65536:
        return False
    if (
        request.headers.get("content-type", "").split(";", 1)[0].lower()
        != "application/json"
    ):
        return False
    parts = urlsplit(request.url).path.rstrip("/").lower().split("/")
    if parts[-1] not in {"search", "jobsearch", "searchjobs"} or not any(
        "job" in part or "career" in part or "position" in part for part in parts
    ):
        return False
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeError):
        return False
    keys = {
        "query",
        "search",
        "keyword",
        "keywords",
        "filter",
        "filters",
        "page",
        "pagesize",
        "limit",
        "offset",
        "sort",
        "locale",
        "location",
        "locations",
        "department",
    }
    return (
        isinstance(payload, dict)
        and bool(payload)
        and all(isinstance(key, str) and key.lower() in keys for key in payload)
        and any(
            key.lower()
            in {"query", "search", "keyword", "keywords", "filter", "filters"}
            for key in payload
        )
    )
