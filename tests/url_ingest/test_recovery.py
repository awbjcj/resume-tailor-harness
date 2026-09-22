import json

import httpx
import pytest

from resume_tailor_harness.discovery.connectors.base import RawJob
from resume_tailor_harness.discovery.url_ingest import recovery, service
from resume_tailor_harness.security.source_cooldown import SourceCooldown

ORIGINAL = "https://www.indeed.com/viewjob?jk=123"
EMPLOYER = "https://jobs.lever.co/acme/123"
HINTS = recovery.RecoveryHints("Acme Inc.", "Staff Engineer", "New York, NY")


def posting(url=EMPLOYER, **overrides):
    values = dict(
        source="url",
        url=url,
        company="Acme",
        title="Staff Engineer",
        location="New York, NY",
        jd_text="Full employer description. " * 20,
        company_provenance="provider",
    )
    return RawJob(**(values | overrides))


def search(*urls):
    return lambda query: json.dumps(
        [
            {"href": url, "body": "Search snippet must never become a job description"}
            for url in urls
        ]
    )


def test_unique_employer_identity_recovers_full_description():
    raw = recovery.recover_employer_posting(
        ORIGINAL, HINTS, search=search(EMPLOYER), reader=lambda url: posting(url)
    )
    assert raw.url == EMPLOYER
    assert raw.jd_text.startswith("Full employer description")


@pytest.mark.parametrize(
    "changes",
    [
        dict(company="Other"),
        dict(title="Senior Engineer"),
        dict(location="London"),
        dict(location=None),
        dict(company_provenance="token"),
    ],
)
def test_mismatches_and_inferred_company_never_auto_recover(changes):
    with pytest.raises(recovery.RecoveryRequired):
        recovery.recover_employer_posting(
            ORIGINAL,
            HINTS,
            search=search(EMPLOYER),
            reader=lambda url: posting(url, **changes),
        )


def test_ambiguous_candidates_are_returned_for_review():
    second = EMPLOYER + "4"
    with pytest.raises(recovery.RecoveryRequired) as caught:
        recovery.recover_employer_posting(
            ORIGINAL, HINTS, search=search(EMPLOYER, second), reader=posting
        )
    assert caught.value.candidates == (EMPLOYER, second)


def test_unreadable_sibling_prevents_false_unique_match():
    second = EMPLOYER + "4"
    with pytest.raises(recovery.RecoveryRequired):
        recovery.recover_employer_posting(
            ORIGINAL,
            HINTS,
            search=search(EMPLOYER, second),
            reader=lambda url: posting(url) if url == EMPLOYER else None,
        )


def test_missing_identity_does_not_search():
    with pytest.raises(recovery.RecoveryRequired, match="Provide company"):
        recovery.recover_employer_posting(
            ORIGINAL, None, search=lambda _: pytest.fail("must not search")
        )


def test_missing_location_is_review_only():
    with pytest.raises(recovery.RecoveryRequired) as caught:
        recovery.recover_employer_posting(
            ORIGINAL,
            recovery.RecoveryHints("Acme", "Staff Engineer"),
            search=search(EMPLOYER),
            reader=posting,
        )
    assert caught.value.candidates == (EMPLOYER,)


@pytest.mark.parametrize("title", ["C# Engineer", "C Engineer"])
def test_recovery_title_identity_preserves_language_punctuation(title):
    hints = recovery.RecoveryHints("Acme", "C++ Engineer", "New York, NY")
    with pytest.raises(recovery.RecoveryRequired):
        recovery.recover_employer_posting(
            ORIGINAL,
            hints,
            search=search(EMPLOYER),
            reader=lambda url: posting(url, title=title),
        )


def test_search_is_bounded_and_third_parties_are_not_fetched():
    seen = []

    def read(url):
        seen.append(url)
        return posting(url)

    with pytest.raises(recovery.RecoveryRequired):
        recovery.recover_employer_posting(
            ORIGINAL,
            HINTS,
            search=search(
                "https://aggregator.test/acme/job",
                *[EMPLOYER + str(i) for i in range(10)],
            ),
            reader=read,
        )
    assert len(seen) == 4
    assert all(url.startswith(EMPLOYER) for url in seen)


@pytest.mark.parametrize(
    "payload",
    ['{"ok":false,"error_code":"SEARCH_RATE_LIMITED"}', '"unexpected"', "not json"],
)
def test_search_failures_are_actionable(payload):
    with pytest.raises(recovery.RecoveryRequired):
        recovery.recover_employer_posting(
            ORIGINAL,
            HINTS,
            search=lambda _: payload,
            reader=lambda _: pytest.fail("must not fetch"),
        )


@pytest.mark.parametrize(
    "blocked",
    [
        httpx.HTTPStatusError(
            "denied",
            request=httpx.Request("GET", ORIGINAL),
            response=httpx.Response(403),
        ),
        SourceCooldown("HTTP 403", 10000),
    ],
)
def test_url_import_recovers_denials_and_active_cooldowns(monkeypatch, blocked):
    def fetch(*args, **kwargs):
        raise blocked

    monkeypatch.setattr(service, "_read_job_url", fetch)
    calls = []

    def recover(url, hints):
        calls.append((url, hints))
        return posting()

    monkeypatch.setattr(service, "recover_employer_posting", recover)
    raw = service.job_from_url(
        ORIGINAL, agent=object(), allow_browser=False, recovery_hints=HINTS
    )
    assert raw.url == EMPLOYER
    assert calls == [(ORIGINAL, HINTS)]


def test_not_found_does_not_trigger_recovery(monkeypatch):
    def missing(*args, **kwargs):
        raise httpx.HTTPStatusError(
            "gone", request=httpx.Request("GET", ORIGINAL), response=httpx.Response(404)
        )

    monkeypatch.setattr(service, "_read_job_url", missing)
    monkeypatch.setattr(
        service,
        "recover_employer_posting",
        lambda *args: pytest.fail("not an access block"),
    )
    with pytest.raises(httpx.HTTPStatusError):
        service.job_from_url(ORIGINAL, agent=object(), recovery_hints=HINTS)


def test_real_candidate_reader_requires_explicit_employer_metadata(monkeypatch):
    from types import SimpleNamespace
    from resume_tailor_harness.discovery.scraper.pacing import CrawlBudget
    from resume_tailor_harness.discovery.scraper.contracts import CrawlLimits
    from resume_tailor_harness.security.outbound import PublicBytesResponse
    from resume_tailor_harness.discovery.url_ingest.models import ExtractedJob

    # An ATS reader's fallback token is insufficient ownership evidence.
    monkeypatch.setitem(
        recovery.ATS_READERS,
        "lever",
        lambda *args: ExtractedJob(
            company="Acme",
            title="Staff Engineer",
            location="New York, NY",
            jd_text="Full employer description. " * 20,
        ),
    )
    payload = {
        "@type": "JobPosting",
        "title": "Staff Engineer",
        "description": "Full description. " * 20,
        "url": EMPLOYER,
        "datePosted": "2026-09-20",
    }

    def read():
        html = '<script type="application/ld+json">' + json.dumps(payload) + "</script>"
        gateway = SimpleNamespace(
            document=lambda *args: PublicBytesResponse(200, {}, html.encode(), EMPLOYER)
        )
        return recovery._read_candidate(EMPLOYER, gateway, CrawlBudget(CrawlLimits()))

    assert read().company_provenance == "unknown"
    payload["hiringOrganization"] = {"name": "Acme Inc."}
    payload["baseSalary"] = {
        "currency": "USD",
        "value": {"minValue": 150000, "maxValue": 190000, "unitText": "YEAR"},
    }
    payload["employmentType"] = "FULL_TIME"
    payload["jobLocationType"] = "TELECOMMUTE"
    payload["applicantLocationRequirements"] = {"name": "United States"}
    raw = read()
    assert raw.company_provenance == "provider"
    assert raw.posted_at.year == 2026
    assert "Compensation: USD 150,000 - 190,000 per year" in raw.jd_text
    assert "Employment Type: Full time" in raw.jd_text
    assert "Workplace Type: Remote (United States)" in raw.jd_text


def test_candidate_redirect_to_unrelated_host_is_not_accepted():
    with pytest.raises(recovery.RecoveryRequired):
        recovery.recover_employer_posting(
            ORIGINAL,
            HINTS,
            search=search(EMPLOYER),
            reader=lambda _: posting("https://unrelated.example/job"),
        )


def test_review_candidates_survive_url_service_error_wrapping(monkeypatch):
    def blocked(*args, **kwargs):
        raise SourceCooldown("HTTP 403", 10000)

    def review(*args):
        raise recovery.RecoveryRequired("Ambiguous", (EMPLOYER,))

    monkeypatch.setattr(service, "_read_job_url", blocked)
    monkeypatch.setattr(service, "recover_employer_posting", review)
    with pytest.raises(recovery.RecoveryRequired) as caught:
        service.job_from_url(ORIGINAL, agent=object(), recovery_hints=HINTS)
    assert caught.value.candidates == (EMPLOYER,)
    assert "retry after" in str(caught.value)
