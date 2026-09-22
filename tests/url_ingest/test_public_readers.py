import json
from types import SimpleNamespace

import pytest

from resume_tailor_harness.discovery.connectors.text import (
    jobposting_json_ld,
    jobposting_meta_lines,
)
from resume_tailor_harness.discovery.scraper.browser_worker import snapshot_from_html
from resume_tailor_harness.discovery.scraper.extract import extract_observation
from resume_tailor_harness.discovery.url_ingest import service
from resume_tailor_harness.discovery.url_ingest.public_readers import (
    read_public_posting,
)


def markup(value):
    return '<script type="application/ld+json">' + json.dumps(value) + "</script>"


def posting(url=None):
    return {
        "@type": ["Thing", "JobPosting"],
        "url": url,
        "title": "Platform Engineer",
        "hiringOrganization": {"name": "Example"},
        "description": "<p>Build reliable services.</p><h2>Requirements</h2><ul><li>Python and SQL</li></ul>",
        "jobLocation": [
            {"address": {"addressLocality": "Toronto", "addressCountry": "CA"}},
            {"address": "New York, US"},
        ],
        "employmentType": ["FULL_TIME", "CONTRACTOR"],
        "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": {"name": "Canada"},
        "baseSalary": [
            {
                "currency": "CAD",
                "value": {"minValue": 40.25, "maxValue": 60.75, "unitText": "HOUR"},
            },
            {"currency": "USD", "value": 55.5, "unitText": "HOUR"},
        ],
        "datePosted": "2026-09-20",
        "validThrough": "2026-10-20",
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://www.indeed.com/viewjob?jk=abc",
        "https://www.glassdoor.com/job-listing/one.htm?jl=123",
        "https://www.ziprecruiter.com/c/Example/Job/Engineer/-in-Toronto?jid=123",
        "https://careers.example.com/jobs/1",
        "https://www.linkedin.com/jobs/view/123",
    ],
)
def test_public_boards_preserve_complete_structured_posting_without_browser_or_llm(
    monkeypatch, url
):
    html = markup(
        {"@graph": [{"@type": "Organization", "name": "Unrelated"}, posting(url)]}
    )
    page = SimpleNamespace(html=html, final_url=url, rendered=False)
    monkeypatch.setattr(service, "fetch_static", lambda _: page)
    monkeypatch.setattr(service, "fetch_page", lambda *a, **k: page)

    class NoAgent:
        def run(self, *_):
            pytest.fail("Structured jobs must not need an LLM")

    job = service.job_from_url(url, agent=NoAgent(), allow_browser=False)
    assert (job.title, job.company) == ("Platform Engineer", "Example")
    assert job.posted_at.isoformat().startswith("2026-09-20")
    for text in (
        "Requirements",
        "Python and SQL",
        "Toronto",
        "New York",
        "CAD 40.25 - 60.75 per hour",
        "USD 55.5 per hour",
        "Remote (Canada)",
        "2026-09-20",
        "2026-10-20",
    ):
        assert text in job.jd_text


def test_item_list_selects_matching_job_and_keeps_meaningful_query_ids():
    url = "https://www.indeed.com/viewjob?jk=wanted&utm_source=email"
    wrong = posting("https://www.indeed.com/viewjob?jk=other")
    wrong["title"] = "Wrong recommendation"
    right = posting("https://www.indeed.com/viewjob?jk=wanted")
    html = markup(
        {"@type": "ItemList", "itemListElement": [{"item": wrong}, {"item": right}]}
    )
    assert jobposting_json_ld(html, url)["title"] == "Platform Engineer"
    result = extract_observation(snapshot_from_html(url, html), "board", 0, None)
    assert result.accepted
    assert len(result.facts.salary_bands) == 2
    assert result.facts.salary_bands[0].minimum == pytest.approx(40.25)
    assert result.facts.remote_policy == "remote"
    assert jobposting_json_ld(html, "https://www.indeed.com/viewjob?jk=missing") is None


@pytest.mark.parametrize(
    "value", [[posting(), posting()], [posting("https://example.com/jobs/other")]]
)
def test_does_not_select_unrelated_or_ambiguous_posting(value):
    assert jobposting_json_ld(markup(value), "https://example.com/jobs/1") is None


@pytest.mark.parametrize(
    "reference",
    ["https://example.com/jobs/other", {"@id": "https://example.com/jobs/other"}],
)
def test_main_entity_reference_cannot_fall_back_to_unrelated_job(reference):
    value = posting()
    value["mainEntityOfPage"] = reference
    assert jobposting_json_ld(markup(value), "https://example.com/jobs/1") is None
    assert (
        jobposting_json_ld(markup(value), "https://example.com/jobs/other")["title"]
        == "Platform Engineer"
    )


def test_empty_description_does_not_become_salary_only_job():
    value = posting()
    value["description"] = ""
    assert (
        read_public_posting(markup(value), "https://careers.example.com/jobs/1") is None
    )


def test_salary_estimate_is_not_reported_as_employer_compensation():
    assert not jobposting_meta_lines(
        {"estimatedSalary": {"currency": "USD", "value": 100000}}
    )


def test_linkedin_sidebar_and_full_body_are_kept():
    html = """<h1 class="top-card-layout__title">Engineer</h1>
    <a class="topcard__org-name-link">Example</a><span class="topcard__flavor--bullet">Toronto</span>
    <div class="show-more-less-html__markup"><p>Build services.</p><ul><li>Python</li></ul></div>
    <li class="description__job-criteria-item"><h3 class="description__job-criteria-subheader">Employment type</h3><span class="description__job-criteria-text">Full-time</span></li>
    <div class="compensation__salary">CAD 40.25/hour</div>"""
    result = read_public_posting(html, "https://www.linkedin.com/jobs/view/1")
    assert result.title == "Engineer"
    assert "Employment Type: Full-time" in result.jd_text
    assert "CAD 40.25/hour" in result.jd_text
    assert "Python" in result.jd_text


def test_microdata_is_scoped_to_one_job():
    html = """<nav>Unrelated menu</nav><article itemscope itemtype="https://schema.org/JobPosting">
    <h1 itemprop="title">Engineer</h1><div itemprop="hiringOrganization">Example</div>
    <div itemprop="description"><p>Build systems.</p></div></article>"""
    result = read_public_posting(html, "https://careers.example.com/jobs/1")
    assert result.title == "Engineer"
    assert result.company == "Example"
    assert result.jd_text == "Build systems."


def test_access_challenge_cannot_be_ingested_even_with_job_markup():
    html = "<h1>Verify you are human</h1>" + markup(posting())
    assert read_public_posting(html, "https://www.indeed.com/viewjob?jk=abc") is None


def test_known_ats_api_survives_a_blocked_presentation_page(monkeypatch):
    import httpx
    from resume_tailor_harness.discovery.url_ingest.models import ExtractedJob

    url = "https://jobs.lever.co/example/one"

    def denied(_):
        raise httpx.HTTPStatusError(
            "blocked", request=httpx.Request("GET", url), response=httpx.Response(403)
        )

    monkeypatch.setattr(service, "fetch_static", denied)
    monkeypatch.setitem(
        service.ATS_READERS,
        "lever",
        lambda *args: ExtractedJob(
            title="Engineer", company="Example", jd_text="Build systems."
        ),
    )
    result = service.job_from_url(url, agent=None, allow_browser=False)
    assert result.jd_text == "Build systems."


def test_challenge_markup_never_supplies_ats_fallback_content(monkeypatch):
    from resume_tailor_harness.security.source_cooldown import SourceCooldown
    from resume_tailor_harness.discovery.url_ingest.models import ExtractedJob

    url = "https://jobs.lever.co/example/one"
    html = "<h1>Verify you are human</h1>" + markup(posting(url))
    monkeypatch.setattr(
        service, "fetch_static", lambda _: SimpleNamespace(html=html, final_url=url)
    )
    monkeypatch.setattr(
        service,
        "default_store",
        lambda: SimpleNamespace(
            block=lambda *args: SourceCooldown("access challenge", 10000)
        ),
    )

    def reader(target, final_url, page_html):
        assert page_html == ""  # Only the independent API can recover a challenge.
        return ExtractedJob(
            title="Verified API role", company="Example", jd_text="API description"
        )

    monkeypatch.setitem(service.ATS_READERS, "lever", reader)
    raw = service.job_from_url(url, agent=None, allow_browser=False)
    assert raw.title == "Verified API role"
    assert "CAD" not in raw.jd_text


def test_ambiguous_board_cannot_be_sent_to_single_job_llm(monkeypatch):
    url = "https://careers.example.com/jobs"
    monkeypatch.setattr(
        service,
        "fetch_static",
        lambda _: SimpleNamespace(html=markup([posting(), posting()]), final_url=url),
    )
    assert service.job_from_url(url, agent=None, allow_browser=False) is None


@pytest.mark.parametrize("key", ["url", "mainEntityOfPage"])
def test_unmatched_single_posting_cannot_bypass_selection_via_llm(monkeypatch, key):
    url = "https://careers.example.com/jobs/wanted"
    value = posting()
    value[key] = "https://careers.example.com/jobs/other"
    html = markup(value) + "<h1>Platform Engineer</h1><p>Build reliable services.</p>"
    monkeypatch.setattr(
        service, "fetch_static", lambda _: SimpleNamespace(html=html, final_url=url)
    )
    monkeypatch.setattr(
        service,
        "extract_fields",
        lambda *args: pytest.fail("Unrelated posting reached the LLM"),
    )
    assert service.job_from_url(url, agent=None, allow_browser=False) is None


def test_malformed_optional_fields_do_not_abort_valid_description():
    value = posting()
    value["hiringOrganization"] = {"name": {"unexpected": True}}
    result = read_public_posting(markup(value), "https://careers.example.com/jobs/1")
    assert result.company is None
    assert "Build reliable services" in result.jd_text


def test_visible_preview_does_not_replace_complete_schema_description():
    value = posting()
    value["description"] = (
        "Build reliable services with our engineering team. " * 12
        + "Final required qualification."
    )
    html = (
        markup(value)
        + '<h1 class="jobsearch-JobInfoHeader-title">Platform Engineer</h1><div id="jobDescriptionText">Build reliable services...</div>'
    )
    result = read_public_posting(html, "https://www.indeed.com/viewjob?jk=abc")
    assert "Final required qualification." in result.jd_text
