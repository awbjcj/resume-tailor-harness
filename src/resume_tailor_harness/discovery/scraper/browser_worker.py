"""A browser child process with application-brokered requests and bounded IPC."""

import json
import multiprocessing
import threading
import time
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing.connection import PipeConnection
from multiprocessing.process import BaseProcess
from typing import Any, Protocol

from bs4 import BeautifulSoup
from resume_tailor_harness.config import get_settings

from resume_tailor_harness.security.browser_gateway import (
    BrowserRequest,
    CrawlStopped,
)
from resume_tailor_harness.security.outbound import PublicBytesResponse

from .contracts import BrowserAction, Snapshot
from .pacing import BudgetExceeded, CrawlBudget


class BrowserGatewayClient(Protocol):
    def fetch(
        self, request: BrowserRequest, budget: CrawlBudget
    ) -> PublicBytesResponse: ...


def snapshot_from_html(
    url: str, html: str, requested_url: str | None = None
) -> Snapshot:
    soup = BeautifulSoup(html, "html.parser")
    dynamic = any(
        tag.get("type") != "application/ld+json" for tag in soup.find_all("script")
    )
    structured = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            structured.append(json.loads(tag.get_text()))
        except (ValueError, TypeError):
            continue
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return Snapshot(
        id=sha256((url + "\n" + html).encode()).hexdigest(),
        requested_url=requested_url or url,
        dynamic=dynamic,
        final_url=url,
        html=html,
        visible_text=soup.get_text("\n", strip=True),
        json_ld=structured,
    )


class _DenyProxy(BaseHTTPRequestHandler):
    def do_CONNECT(self):
        self.send_error(403)

    def do_GET(self):
        self.send_error(403)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _browser_main(pipe):
    from playwright.sync_api import sync_playwright

    proxy = ThreadingHTTPServer(("127.0.0.1", 0), _DenyProxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                chromium_sandbox=True,
                proxy={
                    "server": f"http://127.0.0.1:{proxy.server_port}",
                    "bypass": "<-loopback>",
                },
                args=[
                    "--disable-quic",
                    "--disable-background-networking",
                    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                ],
            )
            context = browser.new_context(
                service_workers="block", accept_downloads=False
            )
            errors = []

            def route_request(route):
                request = route.request
                if request.resource_type in {"image", "media"}:
                    route.abort()
                    return
                pipe.send(
                    (
                        "request",
                        BrowserRequest(
                            request.url,
                            request.method,
                            dict(request.headers),
                            request.post_data_buffer,
                            request.resource_type,
                        ),
                    )
                )
                kind, response = pipe.recv()
                if kind == "response":
                    route.fulfill(
                        status=response.status,
                        headers=response.headers,
                        body=response.body,
                    )
                else:
                    errors.append(str(response))
                    route.abort()

            context.route("**/*", route_request)
            context.route_web_socket("**/*", lambda ws: ws.close())
            page = context.new_page()
            page_stack = []
            page.set_default_timeout(15000)
            pipe.send(("ready", None))
            while True:
                command, data = pipe.recv()
                if command == "close":
                    break
                errors.clear()
                try:
                    action = BrowserAction.model_validate(data)
                    if action.kind == "navigate":
                        if action.url is None:
                            raise ValueError("navigation requires a public URL")
                        page.goto(
                            action.url, wait_until="domcontentloaded", timeout=20000
                        )
                    elif action.kind == "open_detail" and action.url:
                        page_stack.append(page)
                        page = context.new_page()
                        page.set_default_timeout(15000)
                        page.goto(
                            action.url, wait_until="domcontentloaded", timeout=20000
                        )
                    elif action.kind == "close_detail" and page_stack:
                        page.close()
                        page = page_stack.pop()
                    elif action.kind == "scroll":
                        page.mouse.wheel(0, 900)
                    elif action.selector:
                        page.locator(action.selector).first.click()
                    else:
                        raise ValueError("action requires an observed selector")
                    # Allow pending content requests/microtasks to settle, bounded by parent deadline.
                    started = stable_since = time.monotonic()
                    html = page.content()
                    while time.monotonic() - started < 8:
                        page.wait_for_timeout(250)
                        current = page.content()
                        if current != html:
                            stable_since = time.monotonic()
                            html = current
                        if (
                            time.monotonic() - started >= 2
                            and time.monotonic() - stable_since >= 1.5
                        ):
                            break
                    if len(html.encode()) > 2_000_000:
                        raise ValueError("rendered page snapshot is too large")
                    pipe.send(("snapshot", (page.url, html, errors.copy())))
                except Exception as exc:
                    pipe.send(("error", f"{type(exc).__name__}: {exc}"))
            context.close()
            browser.close()
    except Exception as exc:
        pipe.send(("error", f"browser unavailable: {type(exc).__name__}: {exc}"))
    finally:
        proxy.shutdown()
        proxy.server_close()
        pipe.close()


class BrowserUnavailable(RuntimeError):
    code = "BROWSER_UNAVAILABLE"


class BrowserWorker:
    def __init__(self, gateway: BrowserGatewayClient):
        self.gateway = gateway
        self._process: BaseProcess | None = None
        self._pipe: PipeConnection[Any, Any] | None = None
        self.errors: list[str] = []
        self._slot = None
        self._renew_at = 0.0
        self._current_url = ""

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def __enter__(self):
        return self

    def _start(self, budget: CrawlBudget) -> None:
        if not get_settings().public_browser_enabled:
            raise BrowserUnavailable(
                "Browser extraction is disabled on this installation"
            )
        if self.alive:
            return
        scheduler = getattr(self.gateway, "scheduler", None)
        if scheduler:
            owner = getattr(self.gateway, "owner", "browser-worker")
            while self._slot is None:
                budget.check_deadline()
                for index in range(2):
                    self._slot = scheduler.acquire(
                        f"browser-slot:{index}",
                        owner,
                        time.time() + max(0, budget.deadline - budget.clock()),
                    )
                    if self._slot:
                        break
                if self._slot is None:
                    time.sleep(0.1)
            self._renew_at = time.monotonic() + 20
        context = multiprocessing.get_context("spawn")
        self._pipe, child = context.Pipe()
        self._process = context.Process(
            target=_browser_main, args=(child,), daemon=True
        )
        self._process.start()
        child.close()
        self._receive(budget)

    def _receive(self, budget: CrawlBudget):
        pipe = self._pipe
        if pipe is None:
            raise RuntimeError("browser worker pipe is unavailable")
        while True:
            budget.check_deadline()
            renew_page = getattr(self.gateway, "renew_page", None)
            if callable(renew_page):
                renew_page()
            if self._slot and time.monotonic() >= self._renew_at:
                scheduler = getattr(self.gateway, "scheduler", None)
                if scheduler is None or not scheduler.renew(self._slot):
                    raise RuntimeError("Browser worker lease expired")
                self._renew_at = time.monotonic() + 20
            if not pipe.poll(0.1):
                if not self.alive:
                    raise RuntimeError("browser worker exited unexpectedly")
                continue
            kind, result = pipe.recv()
            if kind == "request":
                try:
                    response = self.gateway.fetch(result, budget)
                    pipe.send(("response", response))
                except Exception as exc:
                    pipe.send(("error", str(exc)))
                    if isinstance(exc, (CrawlStopped, BudgetExceeded)):
                        raise
            elif kind == "error":
                if result.startswith("browser unavailable:"):
                    raise BrowserUnavailable(result)
                raise RuntimeError(result)
            else:
                return result

    def snapshot(self, url: str, budget: CrawlBudget) -> Snapshot:
        return self.act(BrowserAction(kind="navigate", url=url), budget)

    def act(self, action: BrowserAction, budget: CrawlBudget) -> Snapshot:
        budget.check_deadline()
        budget.begin_page()
        try:
            self._start(budget)
            begin_page = getattr(self.gateway, "begin_page", None)
            if callable(begin_page):
                begin_page(action.url or self._current_url, budget)
            pipe = self._pipe
            if pipe is None:
                raise RuntimeError("browser worker pipe is unavailable")
            pipe.send(("action", action.model_dump()))
            url, html, self.errors = self._receive(budget)
            self._current_url = url
            snapshot = snapshot_from_html(url, html, action.url)
            headers = getattr(self.gateway, "response_headers", {}).get(url, {})
            snapshot.etag = headers.get("etag")
            snapshot.last_modified = headers.get("last-modified")
            return snapshot
        finally:
            end_page = getattr(self.gateway, "end_page", None)
            if callable(end_page):
                end_page()

    def __exit__(self, *_args):
        process = self._process
        pipe = self._pipe
        if self.alive:
            try:
                if pipe is not None and process is not None:
                    pipe.send(("close", None))
                    process.join(timeout=2)
            except (BrokenPipeError, EOFError, OSError):
                pass
            if self.alive:
                if process is not None:
                    process.terminate()
                    process.join(timeout=3)
        if pipe:
            pipe.close()
        if self._slot:
            scheduler = getattr(self.gateway, "scheduler", None)
            if scheduler is not None:
                scheduler.release(self._slot, 0)
            self._slot = None
