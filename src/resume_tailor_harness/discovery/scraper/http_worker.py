"""Replay public links and inline cards through the same bounded egress gateway."""

from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from resume_tailor_harness.discovery.url_ingest.public_readers import access_blocked
from resume_tailor_harness.security.browser_gateway import CrawlStopped
from .browser_worker import BrowserUnavailable, snapshot_from_html
from .contracts import BrowserAction, Snapshot
from .pacing import CrawlBudget


class HttpWorker:
    def __init__(self, gateway, initial: Snapshot | None = None):
        self.gateway = gateway
        self.errors: list[str] = []
        self.current: Snapshot | None = initial
        self._initial = initial
        self._listing: Snapshot | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def snapshot(self, url: str, budget: CrawlBudget) -> Snapshot:
        budget.check_deadline()
        if self._initial and url in {
            self._initial.requested_url,
            self._initial.final_url,
        }:
            result, self._initial = self._initial, None
        else:
            budget.begin_page()
            response = self.gateway.document(url, budget)
            if response.status != 200:
                if response.status in {401, 403, 429}:
                    raise CrawlStopped(
                        "throttled" if response.status == 429 else "blocked",
                        f"Website returned HTTP {response.status}",
                    )
                raise ValueError(f"Website returned HTTP {response.status}")
            content_type = (
                response.headers.get("content-type", "text/html")
                .split(";", 1)[0]
                .lower()
            )
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError("Expected a public HTML job page")
            result = snapshot_from_html(
                response.final_url, response.body.decode("utf-8", errors="replace"), url
            )
            result.etag = response.headers.get("etag")
            result.last_modified = response.headers.get("last-modified")
        if access_blocked(result.html):
            if cooldowns := getattr(self.gateway, "cooldowns", None):
                cooldown = cooldowns.block(result.final_url, "access challenge")
                raise CrawlStopped(
                    "blocked", f"The site returned an access challenge; {cooldown}"
                )
            raise CrawlStopped("blocked", "The site returned an access challenge")
        self.current = result
        self.errors = []
        return result

    def act(self, action: BrowserAction, budget: CrawlBudget) -> Snapshot:
        budget.check_deadline()
        if action.kind == "close_detail":
            if self._listing is not None:
                self.current, self._listing = self._listing, None
            if self.current is None:
                raise ValueError("No listing to return to")
            return self.current
        if action.kind == "open_detail":
            if not action.url:
                raise BrowserUnavailable(
                    "This detail panel requires JavaScript; use a public posting URL"
                )
            self._listing = self.current
        if action.kind in {"navigate", "open_detail"} and action.url:
            return self.snapshot(action.url, budget)
        if action.kind == "next" and self.current is not None:
            node = BeautifulSoup(self.current.html, "html.parser").select_one(
                action.selector or ""
            )
            href = node.get("href") if node is not None else None
            if isinstance(href, str) and href.strip():
                url = urljoin(self.current.final_url, href)
                if (
                    urlsplit(url).scheme in {"http", "https"}
                    and url != self.current.final_url
                ):
                    return self.snapshot(url, budget)
        raise BrowserUnavailable(
            "This page requires JavaScript navigation; HTTP extraction retained the inspected jobs"
        )
