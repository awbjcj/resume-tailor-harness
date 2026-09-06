"""A browser child process with application-brokered requests and bounded IPC."""

import json
import multiprocessing
import threading
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bs4 import BeautifulSoup

from resume_tailor_harness.security.browser_gateway import (
    BrowserGateway,
    BrowserRequest,
)

from .contracts import BrowserAction, Snapshot
from .pacing import CrawlBudget


def snapshot_from_html(
    url: str, html: str, requested_url: str | None = None
) -> Snapshot:
    soup = BeautifulSoup(html, "html.parser")
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

    def log_message(self, *_args):
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
                        page.goto(
                            action.url, wait_until="domcontentloaded", timeout=20000
                        )
                    elif action.kind == "scroll":
                        page.mouse.wheel(0, 900)
                    elif action.selector:
                        page.locator(action.selector).first.click()
                    else:
                        raise ValueError("action requires an observed selector")
                    # Allow pending content requests/microtasks to settle, bounded by parent deadline.
                    page.wait_for_timeout(350)
                    html = page.content()
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


class BrowserWorker:
    def __init__(self, gateway: BrowserGateway):
        self.gateway = gateway
        self._process = None
        self._pipe = None
        self.errors: list[str] = []

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def __enter__(self):
        return self

    def _start(self, budget: CrawlBudget) -> None:
        if self.alive:
            return
        context = multiprocessing.get_context("spawn")
        self._pipe, child = context.Pipe()
        self._process = context.Process(
            target=_browser_main, args=(child,), daemon=True
        )
        self._process.start()
        child.close()
        self._receive(budget)

    def _receive(self, budget: CrawlBudget):
        while True:
            budget.check_deadline()
            if not self._pipe.poll(0.1):
                if not self.alive:
                    raise RuntimeError("browser worker exited unexpectedly")
                continue
            kind, result = self._pipe.recv()
            if kind == "request":
                try:
                    response = self.gateway.fetch(result, budget)
                    self._pipe.send(("response", response))
                except Exception as exc:
                    self._pipe.send(("error", str(exc)))
            elif kind == "error":
                raise RuntimeError(result)
            else:
                return result

    def snapshot(self, url: str, budget: CrawlBudget) -> Snapshot:
        return self.act(BrowserAction(kind="navigate", url=url), budget)

    def act(self, action: BrowserAction, budget: CrawlBudget) -> Snapshot:
        budget.check_deadline()
        budget.begin_page()
        self._start(budget)
        self._pipe.send(("action", action.model_dump()))
        url, html, self.errors = self._receive(budget)
        return snapshot_from_html(url, html, action.url)

    def __exit__(self, *_args):
        if self.alive:
            try:
                self._pipe.send(("close", None))
                self._process.join(timeout=2)
            except (BrokenPipeError, EOFError, OSError):
                pass
            if self.alive:
                self._process.terminate()
                self._process.join(timeout=3)
        if self._pipe:
            self._pipe.close()
