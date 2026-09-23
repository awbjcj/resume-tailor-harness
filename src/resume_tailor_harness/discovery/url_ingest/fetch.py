from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from resume_tailor_harness.discovery.url_ingest.browser import fetch_rendered
from resume_tailor_harness.discovery.url_ingest.models import PageContent
from resume_tailor_harness.discovery.connectors.text import jobposting_json_ld
from resume_tailor_harness.discovery.scraper.pacing import retry_delay
from resume_tailor_harness.security.source_cooldown import default_store
from resume_tailor_harness.security.outbound import (
    Resolver,
    fetch_public_text,
    resolve_host,
    validate_public_url,
)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; resume-tailor-harness/1.0)"}
_LINKEDIN_DETAIL_SELECTOR = "div.show-more-less-html__markup, .description__text"
_SHELL_TEXT_THRESHOLD = 200


def is_linkedin(host: str) -> bool:
    """The single LinkedIn host rule, shared by fetch (render) and service (route)."""
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def _looks_like_js_shell(html: str) -> bool:
    posting = jobposting_json_ld(html)
    if (
        posting
        and isinstance(posting.get("description"), str)
        and posting["description"].strip()
    ):
        return False
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body = soup.body or soup
    return len(body.get_text(" ", strip=True)) < _SHELL_TEXT_THRESHOLD


def fetch_static(
    url: str,
    *,
    client: httpx.Client | None = None,
    resolver: Resolver = resolve_host,
) -> PageContent:
    """Plain, non-browser GET. Known-ATS hosts use only this -- never the browser."""
    cooldowns = default_store()
    cooldowns.check(url)
    try:
        response = fetch_public_text(
            url,
            client=client,
            resolver=resolver,
            max_bytes=2_000_000,
            timeout=20.0,
            headers=_HEADERS,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {401, 403, 429, 503}:
            seconds = (
                retry_delay(exc.response.headers.get("retry-after"), 0)
                if status in {429, 503}
                else 3600
            )
            cooldowns.block(
                str(exc.request.url),
                f"HTTP {status}",
                seconds=seconds,
                origin_only=status in {429, 503},
            )
            # Also gate a tracking URL that redirected to the blocked source.
            cooldown = cooldowns.block(url, f"HTTP {status}", seconds=seconds)
            raise cooldown from exc
        raise
    return PageContent(
        html=response.text,
        final_url=response.final_url,
        rendered=False,
    )


def upgrade_if_shell(page: PageContent, *, allow_browser: bool = True) -> PageContent:
    """Re-fetch an already-fetched page in a browser when it is a JS shell.

    Takes the ``PageContent`` the caller already holds rather than a URL, so a
    caller that has fetched statically to route the URL does not pay a second
    request against the same host just to apply the shell policy.
    """
    if not allow_browser or not _looks_like_js_shell(page.html):
        return page
    validate_public_url(page.final_url)
    return PageContent(
        html=fetch_rendered(page.final_url), final_url=page.final_url, rendered=True
    )


def fetch_page(url: str, *, allow_browser: bool = True) -> PageContent:
    """Fetch a posting page. HTTP-first; render only when public job content is missing."""
    page = fetch_static(url)
    host = urlsplit(page.final_url).netloc.lower()
    if is_linkedin(host):
        soup = BeautifulSoup(page.html, "html.parser")
        if soup.select_one(_LINKEDIN_DETAIL_SELECTOR) is not None or jobposting_json_ld(
            page.html, page.final_url
        ):
            return page
        if allow_browser:
            validate_public_url(page.final_url)
            return PageContent(
                html=fetch_rendered(
                    page.final_url, wait_selector=_LINKEDIN_DETAIL_SELECTOR
                ),
                final_url=page.final_url,
                rendered=True,
            )
        return page
    return upgrade_if_shell(page, allow_browser=allow_browser)
