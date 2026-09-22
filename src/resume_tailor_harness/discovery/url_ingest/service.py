from urllib.parse import urlsplit

import httpx

from resume_tailor_harness.discovery.connectors.base import RawJob
from resume_tailor_harness.discovery.connectors.dates import parse_iso_datetime
from resume_tailor_harness.discovery.connectors.detect import (
    SINGLETON_ATS,
    identify_host,
)
from resume_tailor_harness.discovery.connectors.text import clean_job_description_text
from resume_tailor_harness.discovery.connectors.jobposting import (
    json_ld,
    postings,
    select_posting,
)
from resume_tailor_harness.discovery.scraper.parser import (
    parse_detail_meta,
    parse_job_detail,
)
from resume_tailor_harness.discovery.url_ingest.ats_readers import (
    ATS_READERS,
    read_employer_hosted_greenhouse,
    with_json_ld_meta,
)
from resume_tailor_harness.discovery.url_ingest.fetch import (
    fetch_page,
    fetch_static,
    is_linkedin,
    upgrade_if_shell,
)
from resume_tailor_harness.discovery.url_ingest.llm import extract_fields, html_to_text
from resume_tailor_harness.discovery.url_ingest.models import ExtractedJob, PageContent
from resume_tailor_harness.discovery.url_ingest.public_readers import (
    access_blocked,
    read_public_posting,
)
from resume_tailor_harness.llm_runner import Runner
from resume_tailor_harness.security.source_cooldown import SourceCooldown, default_store
from resume_tailor_harness.discovery.url_ingest.recovery import (
    RecoveryHints,
    RecoveryRequired,
    recover_employer_posting,
)


def job_from_url(
    url: str,
    *,
    agent: Runner,
    allow_browser: bool = True,
    recovery_hints: RecoveryHints | None = None,
) -> RawJob | None:
    """Fetch a posting, recovering a blocked source only from verified employer content."""
    try:
        return _read_job_url(url, agent=agent, allow_browser=allow_browser)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {401, 403, 429, 503}:
            raise
        reason = f"HTTP {exc.response.status_code}"
    except SourceCooldown as exc:
        reason = str(exc)
    try:
        return recover_employer_posting(url, recovery_hints)
    except RecoveryRequired as exc:
        raise RecoveryRequired(f"{reason}. {exc.message}", exc.candidates) from exc


def _reject_challenge(page: PageContent) -> None:
    if access_blocked(page.html):
        raise default_store().block(page.final_url, "access challenge")


def read_linkedin_posting(html: str) -> ExtractedJob:
    """Read a single posting page into structured fields."""
    meta = parse_detail_meta(html)
    return ExtractedJob(
        title=meta.title,
        company=meta.company,
        location=meta.location,
        jd_text=parse_job_detail(html),
    )


def _read_job_url(
    url: str, *, agent: Runner, allow_browser: bool = True
) -> RawJob | None:
    """Import a public posting through ATS APIs, structured data, then visible text.

    Known ATS readers never render. A failed presentation-page request may
    still resolve through the provider API. Other pages use JSON-LD or scoped
    semantic markup before LLM extraction, preserving richer employer prose.
    Rendering remains an optional fallback, always disabled by allow_browser=False.
    Ambiguous boards, access challenges and empty bodies are not job postings.
    """
    host = urlsplit(url).netloc.lower()
    source_page: PageContent
    if is_linkedin(host):
        page = fetch_page(url, allow_browser=allow_browser)
        source_page = page
        _reject_challenge(page)
        extracted = read_public_posting(
            page.html, page.final_url
        ) or read_linkedin_posting(page.html)
    else:
        fetch_error = None
        try:
            static_page = fetch_static(url)
            _reject_challenge(static_page)
        except (httpx.HTTPError, SourceCooldown) as exc:
            target = identify_host(url)
            if target is None or target.ats not in ATS_READERS:
                raise
            # An unavailable presentation page need not take its public ATS API
            # down with it. The original error still wins if that lookup fails.
            fetch_error = exc
            static_page = PageContent(html="", final_url=url, rendered=False)
        source_page = static_page
        # Route on the post-redirect URL: a tracking or shortened link only
        # reveals the real host after the fetch.
        if is_linkedin(urlsplit(static_page.final_url).netloc.lower()):
            page = fetch_page(static_page.final_url, allow_browser=allow_browser)
            source_page = page
            _reject_challenge(page)
            extracted = read_public_posting(
                page.html, page.final_url
            ) or read_linkedin_posting(page.html)
        else:
            target = identify_host(static_page.final_url)
            extracted = read_employer_hosted_greenhouse(static_page.html)
            if extracted is None and target is not None:
                reader = ATS_READERS.get(target.ats)
                if reader is not None:
                    extracted = reader(target, static_page.final_url, static_page.html)
            if extracted is None:
                extracted = read_public_posting(static_page.html, static_page.final_url)
            if extracted is not None:
                extracted = with_json_ld_meta(
                    extracted, static_page.html, static_page.final_url
                )
            else:
                if fetch_error is not None:
                    raise fetch_error
                _reject_challenge(static_page)
                data = json_ld(static_page.html)
                if (
                    any(postings(data))
                    and select_posting(data, static_page.final_url) is None
                ):
                    return None
                if target is not None and target.ats not in SINGLETON_ATS:
                    page = static_page
                else:
                    page = upgrade_if_shell(static_page, allow_browser=allow_browser)
                source_page = page
                _reject_challenge(page)
                if not html_to_text(page.html).strip():
                    return None
                extracted = with_json_ld_meta(
                    extract_fields(html_to_text(page.html), agent),
                    page.html,
                    page.final_url,
                )
    if extracted is None:
        return None
    jd_text = clean_job_description_text(extracted.jd_text)
    if not jd_text:
        return None
    selected = select_posting(json_ld(source_page.html), source_page.final_url)
    posted = selected[1].get("datePosted") if selected else None
    return RawJob(
        source="url",
        url=url,
        company=extracted.company,
        title=extracted.title,
        location=extracted.location,
        jd_text=jd_text,
        posted_at=parse_iso_datetime(posted) if isinstance(posted, str) else None,
    )
