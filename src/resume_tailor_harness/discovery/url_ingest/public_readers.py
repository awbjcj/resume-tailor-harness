"""Deterministic readers for public job markup; no script execution or guesses."""

from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from resume_tailor_harness.discovery.connectors.text import (
    html_to_markdown,
    with_meta_lines,
    jobposting_json_ld,
    is_materially_richer,
)
from .ats_readers import _from_json_ld, with_json_ld_meta
from .models import ExtractedJob


def access_blocked(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    headings = " ".join(
        node.get_text(" ", strip=True).casefold()
        for node in soup.select("title, h1, h2")
    )
    return any(
        phrase in headings
        for phrase in (
            "access denied",
            "verify you are human",
            "security verification",
            "just a moment",
            "captcha",
            "sign in to continue",
            "robot check",
        )
    )


def read_public_posting(html: str, url: str) -> ExtractedJob | None:
    if access_blocked(html):
        return None
    structured = _from_json_ld(html, url)
    soup = BeautifulSoup(html, "html.parser")
    host = (urlsplit(url).hostname or "").lower()
    # Restrict provider-specific CSS to that provider; hashed classes are avoided.
    selectors = {
        "linkedin.com": (
            ".show-more-less-html__markup, .description__text",
            ".top-card-layout__title",
            ".topcard__org-name-link",
            ".topcard__flavor--bullet",
        ),
        "indeed.com": (
            "#jobDescriptionText",
            "h1.jobsearch-JobInfoHeader-title",
            '[data-testid="inlineHeader-companyName"]',
            '[data-testid="job-location"]',
        ),
        "glassdoor.com": (
            '[data-test="jobDescriptionContent"]',
            '[data-test="job-title"]',
            '[data-test="employer-name"]',
            '[data-test="location"]',
        ),
        "ziprecruiter.com": (
            '[data-testid="job_description"], .job_description',
            "h1.job_title",
            ".hiring_company",
            ".job_location",
        ),
    }
    selected = next(
        (
            value
            for domain, value in selectors.items()
            if host == domain or host.endswith("." + domain)
        ),
        None,
    )
    if selected is None:
        # Microdata explicitly scopes one JobPosting, not the site's generic main.
        scopes = soup.select('[itemscope][itemtype$="/JobPosting"]')
        if len(scopes) != 1:
            # A short schema blurb must not suppress extraction of richer visible
            # employer sections (attendance, benefits, qualifications).
            posting = jobposting_json_ld(html, url)
            raw_description = posting.get("description") if posting else None
            description = (
                html_to_markdown(raw_description)
                if isinstance(raw_description, str)
                else ""
            )
            for node in soup.select("script, style, nav, footer, header"):
                node.decompose()
            visible = soup.get_text(" ", strip=True)
            if structured and (
                is_materially_richer(visible, description)
                or (
                    len(description.split()) < 40
                    and len(visible.split()) > len(description.split()) + 5
                )
            ):
                return None
            return structured
        soup = scopes[0]
        selected = (
            '[itemprop="description"]',
            '[itemprop="title"]',
            '[itemprop="hiringOrganization"]',
            '[itemprop="jobLocation"]',
        )

    def text(selector):
        node = soup.select_one(selector)
        return node.get_text(" ", strip=True) or node.get("content") if node else None

    body = soup.select_one(selected[0])
    title = text(selected[1]) or (structured.title if structured else None)
    if body is None or not title:
        return structured
    description = html_to_markdown(str(body))
    if not description:
        return structured
    posting = jobposting_json_ld(html, url)
    schema_description = posting.get("description") if posting else None
    if isinstance(schema_description, str):
        schema_body = html_to_markdown(schema_description)
        if is_materially_richer(schema_body, description):
            description = schema_body
    lines = []
    location = text(selected[3]) or (structured.location if structured else None)
    if location:
        lines.append(f"Location: {location}")
    for prop, label in (
        ("employmentType", "Employment Type"),
        ("baseSalary", "Compensation"),
        ("jobLocationType", "Workplace Type"),
        ("applicantLocationRequirements", "Remote Restrictions"),
        ("datePosted", "Date Posted"),
        ("validThrough", "Valid Through"),
        ("qualifications", "Qualifications"),
        ("educationRequirements", "Education"),
        ("experienceRequirements", "Experience"),
    ):
        if value := text(f'[itemprop="{prop}"]'):
            lines.append(f"{label}: {value}")
    for item in soup.select(".description__job-criteria-item"):
        label = item.select_one(".description__job-criteria-subheader")
        value = item.select_one(".description__job-criteria-text")
        if label and value:
            name = label.get_text(" ", strip=True)
            name = {
                "Seniority level": "Experience Level",
                "Employment type": "Employment Type",
                "Industries": "Industry",
                "Job function": "Job Function",
            }.get(name, name)
            lines.append(f"{name}: {value.get_text(' ', strip=True)}")
    for node in soup.select(
        ".salary.compensation__salary, .compensation__salary, #salaryInfoAndJobType"
    ):
        lines.append(f"Compensation: {node.get_text(' ', strip=True)}")
    result = ExtractedJob(
        title=title,
        company=text(selected[2]) or (structured.company if structured else None),
        location=location,
        jd_text=with_meta_lines(lines, description),
    )
    return with_json_ld_meta(result, html, url)
