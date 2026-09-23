"""Conservative employer-posting recovery. Search results are leads, never JDs."""

import json
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from resume_tailor_harness.discovery.connectors.base import RawJob
from resume_tailor_harness.discovery.connectors.detect import identify_host
from resume_tailor_harness.discovery.connectors.text import jobposting_json_ld
from resume_tailor_harness.discovery.connectors.dates import parse_iso_datetime
from resume_tailor_harness.discovery.source_resolution.identity import (
    normalize_company_name,
    registrable_domain,
)
from resume_tailor_harness.discovery.source_resolution.search import (
    SearchBudget,
    make_budgeted_web_search_tool,
)
from resume_tailor_harness.discovery.url_ingest.ats_readers import (
    ATS_READERS,
    with_json_ld_meta,
)
from resume_tailor_harness.discovery.url_ingest.public_readers import (
    read_public_posting,
)
from resume_tailor_harness.discovery.scraper.contracts import CrawlLimits
from resume_tailor_harness.discovery.scraper.pacing import CrawlBudget, BudgetExceeded
from resume_tailor_harness.discovery.scraper.http_worker import HttpWorker


@dataclass(frozen=True)
class RecoveryHints:
    company: str
    title: str
    location: str | None = None


class RecoveryRequired(ValueError):
    """Reviewable failure, surfaced through existing import/run error views."""

    def __init__(self, message: str, candidates: tuple[str, ...] = ()):
        self.message = message
        self.candidates = candidates
        links = " Candidates to review: " + "; ".join(candidates) if candidates else ""
        super().__init__(message + links)


def _normalized(value: str | None) -> str:
    return re.sub(
        r"[^\w]+", " ", unicodedata.normalize("NFKC", value or "").casefold()
    ).strip()


def _title_identity(value: str | None) -> str:
    # Punctuation distinguishes roles such as C++, C# and C engineers.
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def _eligible(url: str, company: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    target = identify_host(url)
    if target and target.ats in ATS_READERS:
        return True
    # Custom careers sites need a company-bound domain as well as matching
    # structured metadata. Do not trust a third-party page's employer claim.
    label = registrable_domain(url).split(".")[0]
    return _normalized(label).replace(" ", "") == normalize_company_name(
        company
    ).replace(" ", "")


def _read_candidate(url: str, gateway, budget: CrawlBudget) -> RawJob | None:
    budget.charge_detail()
    snapshot = HttpWorker(gateway).snapshot(url, budget)
    html = snapshot.html
    target = identify_host(snapshot.final_url)
    extracted = None
    if target and (reader := ATS_READERS.get(target.ats)):
        extracted = reader(target, snapshot.final_url, html)
    extracted = extracted or read_public_posting(html, snapshot.final_url)
    extracted = with_json_ld_meta(extracted, html, snapshot.final_url)
    if extracted is None or len(extracted.jd_text.strip()) < 200:
        return None
    posting = jobposting_json_ld(html, snapshot.final_url) or {}
    organization = posting.get("hiringOrganization")
    name = organization.get("name") if isinstance(organization, dict) else None
    proven = isinstance(name, str) and normalize_company_name(
        name
    ) == normalize_company_name(extracted.company or "")
    posted = posting.get("datePosted")
    return RawJob(
        source="url",
        url=snapshot.final_url,
        company=extracted.company,
        title=extracted.title,
        location=extracted.location,
        jd_text=extracted.jd_text,
        company_provenance="provider" if proven else "unknown",
        posted_at=parse_iso_datetime(posted) if isinstance(posted, str) else None,
    )


def recover_employer_posting(
    url: str, hints: RecoveryHints | None, *, search=None, reader=None
) -> RawJob:
    if not hints or not hints.company.strip() or not hints.title.strip():
        raise RecoveryRequired(
            "Source unavailable. Provide company, title and location, or import the employer's posting URL."
        )
    search = search or make_budgeted_web_search_tool(SearchBudget(max_uses=1))
    query = (
        " ".join(
            json.dumps(value)
            for value in (hints.company, hints.title, hints.location)
            if value
        )
        + " careers job"
    )
    try:
        payload = json.loads(search(query))
    except (ValueError, httpx.HTTPError) as exc:
        raise RecoveryRequired(
            "Employer search unavailable; import the employer's posting URL."
        ) from exc
    if isinstance(payload, dict):
        if payload.get("ok") is False:
            raise RecoveryRequired(
                "Employer search unavailable or rate limited; try later or import the employer's posting URL."
            )
        payload = payload.get("results", [])
    if not isinstance(payload, list):
        raise RecoveryRequired("Employer search returned no usable leads.")
    urls = []
    for row in payload[:5]:
        candidate = (
            row.get("href") or row.get("url") or row.get("link")
            if isinstance(row, dict)
            else None
        )
        if (
            isinstance(candidate, str)
            and candidate != url
            and _eligible(candidate, hints.company)
            and candidate not in urls
        ):
            urls.append(candidate)
    if not urls:
        raise RecoveryRequired(
            "No employer posting leads found. Import the employer's posting URL directly."
        )
    if reader is None:
        from resume_tailor_harness.services.scrape_review import build_gateway

        gateway = build_gateway()
        budget = CrawlBudget(CrawlLimits(detail_pages=5, elapsed_seconds=90))

        def reader(candidate):
            return _read_candidate(candidate, gateway, budget)

    matches: dict[str, RawJob] = {}
    review: list[str] = []
    unresolved = False
    for candidate in urls:
        try:
            raw = reader(candidate)
        except (httpx.HTTPError, ValueError, BudgetExceeded):
            unresolved = True
            review.append(candidate)
            continue
        if not raw or not raw.url:
            unresolved = True
            review.append(candidate)
            continue
        if not _eligible(raw.url, hints.company):
            continue
        if normalize_company_name(raw.company or "") != normalize_company_name(
            hints.company
        ) or _title_identity(raw.title) != _title_identity(hints.title):
            continue
        review.append(raw.url)
        if (
            raw.company_provenance == "provider"
            and hints.location
            and _normalized(raw.location) == _normalized(hints.location)
        ):
            matches[raw.url] = raw
    if len(matches) == 1 and len(set(review)) == 1 and not unresolved:
        return next(iter(matches.values()))
    raise RecoveryRequired(
        "Could not uniquely verify the employer posting. Review the candidates; the original job has been preserved.",
        tuple(dict.fromkeys(review)),
    )
