"""Bounded LinkedIn public search and full-detail acquisition without a browser."""

from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

from resume_tailor_harness.discovery.connectors.base import (
    FetchResult,
    RawJob,
    SkipSeen,
)
from resume_tailor_harness.discovery.connectors.text import (
    relevance_gate,
    title_relevance_gate,
)
from resume_tailor_harness.discovery.search_config import SearchConfig
from resume_tailor_harness.discovery.url_ingest.public_readers import (
    read_public_posting,
)
from resume_tailor_harness.security.browser_gateway import CrawlStopped
from resume_tailor_harness.discovery.url_ingest.recovery import (
    RecoveryHints,
    RecoveryRequired,
    recover_employer_posting,
)
from .contracts import CrawlLimits
from .http_worker import HttpWorker
from .linkedin import _search_url, _source_searches
from .pacing import BudgetExceeded, CrawlBudget
from .parser import parse_search_cards


class LinkedInHttpScraper:
    name = "linkedin"
    concurrent_fetch = True

    def __init__(self, configured_limit: int | None = None, *, gateway=None):
        self.configured_limit = configured_limit
        self.gateway = gateway

    def fetch(
        self,
        search: SearchConfig,
        limit: int | None = None,
        skip_seen: SkipSeen | None = None,
    ) -> FetchResult:
        from resume_tailor_harness.services.scrape_review import build_gateway

        limit = self.configured_limit if self.configured_limit is not None else limit
        if limit is not None and limit <= 0:
            return FetchResult(jobs=[])
        cap = min(limit if limit is not None else 50, 200)
        budget = CrawlBudget(CrawlLimits(detail_pages=200))
        result = FetchResult(jobs=[])
        worker = HttpWorker(self.gateway or build_gateway())
        seen: set[str] = set()
        recovery_attempts = 0
        current_url = "https://www.linkedin.com/jobs/search/"
        try:
            for query in _source_searches(search, limit):
                params = dict(
                    parse_qsl(
                        urlsplit(_search_url(query, geo_resolver=lambda _: None)).query
                    )
                )
                offset = 0
                while len(result.jobs) < cap:
                    budget.charge_listing()
                    current_url = (
                        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                        + urlencode({**params, "start": offset})
                    )
                    page = worker.snapshot(current_url, budget)
                    cards = parse_search_cards(page.html)
                    if not cards:
                        if (
                            page.visible_text.strip()
                            and "no matching jobs" not in page.visible_text.casefold()
                        ):
                            result.failures[current_url] = (
                                "Public search returned no recognizable job cards; access or layout may have changed"
                            )
                        break
                    new_count = 0
                    for card in cards:
                        if not card.url or card.url in seen:
                            continue
                        seen.add(card.url)
                        new_count += 1
                        raw = RawJob(
                            source="linkedin",
                            url=card.url,
                            company=card.company,
                            title=card.title,
                            location=card.location,
                            jd_text="",
                            posted_at=card.posted_at,
                        )
                        if not title_relevance_gate([raw], search):
                            result.filtered += 1
                            continue
                        if skip_seen and skip_seen(raw):
                            continue
                        budget.charge_detail()
                        try:
                            detail = worker.snapshot(card.url, budget)
                            extracted = read_public_posting(
                                detail.html, detail.final_url
                            )
                            if not extracted or not extracted.jd_text:
                                result.failures[card.url] = (
                                    "Full public job description unavailable"
                                )
                                continue
                            raw.title = extracted.title or raw.title
                            raw.company = extracted.company or raw.company
                            raw.location = extracted.location or raw.location
                            raw.jd_text = extracted.jd_text
                            if relevance_gate([raw], search):
                                result.jobs.append(raw)
                            else:
                                result.filtered += 1
                        except CrawlStopped as exc:
                            if recovery_attempts >= 3:
                                raise
                            recovery_attempts += 1
                            try:
                                recovered = recover_employer_posting(
                                    card.url,
                                    RecoveryHints(
                                        card.company or "",
                                        card.title or "",
                                        card.location,
                                    ),
                                )
                                if relevance_gate([recovered], search):
                                    result.jobs.append(recovered)
                                else:
                                    result.filtered += 1
                            except RecoveryRequired as recovery:
                                result.failures[card.url] = f"{exc}. {recovery}"
                        except BudgetExceeded:
                            raise
                        except (httpx.HTTPError, ValueError) as exc:
                            result.failures[card.url] = str(exc)
                        if len(result.jobs) >= cap:
                            return result
                    if not new_count:
                        result.failures[current_url] = (
                            "Public search repeated its previous page"
                        )
                        break
                    offset += len(cards)
        except (CrawlStopped, BudgetExceeded, httpx.HTTPError, ValueError) as exc:
            result.failures[current_url] = str(exc)
        return result
