"""Metadata formatting must be consistent in real exported PDFs."""

import pytest
from pypdf import PdfReader

from resume_tailor_harness.models.profile import Contact, Education
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredExperience,
    TailoredProject,
    TailoredSkill,
    TailoredVolunteer,
)
from resume_tailor_harness.render.renderer import render_pdf
from resume_tailor_harness.render.formatting import (
    format_date,
    format_label,
    format_resume_metadata,
)
from resume_tailor_harness.render.templates import BUNDLED


def _mixed_metadata() -> ResumeContent:
    return ResumeContent(
        contact=Contact(name="Alex Sample"),
        experience=[
            TailoredExperience(
                company="OpenAI",
                title="senior API engineer",
                start="2022-08",
                end="September 2022",
                provenance="experience",
            )
        ],
        projects=[
            TailoredProject(
                name="VSDA Deep Agent",
                role="  sole   author  ",
                start="2026-03",
                provenance="vsda",
            ),
            TailoredProject(
                name="Résumé Tailor Harness",
                role="Sole author and maintainer",
                start="June 2026",
                end="current",
                provenance="resume-tailor",
            ),
        ],
        portfolio=[
            TailoredProject(
                name="Integration Toolkit",
                role="iOS and eBay contributor",
                start="2024",
                end="2025",
                provenance="portfolio",
            )
        ],
        skills={"AI & data": [TailoredSkill(name="FastAPI", provenance="fastapi")]},
        education=[Education(institution="State University", end="Sept. 2022")],
        volunteer=[
            TailoredVolunteer(
                organization="Engineering Club",
                role="open-source maintainer",
                start="2023",
                end="2024",
                provenance="volunteer",
            )
        ],
    )


@pytest.mark.parametrize("template_id", BUNDLED)
def test_metadata_is_consistent_across_resume_sections(tmp_path, template_id):
    content = _mixed_metadata()
    original = content.model_dump_json()
    path = render_pdf(
        content,
        tmp_path / f"{template_id}.pdf",
        BUNDLED[template_id].path,
        fit_pages=None,
    )
    text = " ".join(
        " ".join(page.extract_text() or "" for page in PdfReader(path).pages).split()
    )

    for expected in (
        "Sole Author",
        "Sole Author and Maintainer",
        "Senior API Engineer",
        "iOS and eBay Contributor",
        "Open-Source Maintainer",
        "AI & Data: FastAPI",
        "Mar 2026 – Present",
        "Jun 2026 – Present",
        "Aug 2022 – Sep 2022",
        "2024 – 2025",
        "VSDA Deep Agent",
        "Résumé Tailor Harness",
        "OpenAI",
    ):
        assert expected in text, f"Missing normalized metadata: {expected}"
    assert "sole author" not in text
    assert "Sept" not in text
    assert "2026-03" not in text
    assert content.model_dump_json() == original


@pytest.mark.parametrize(
    "source,expected",
    [
        ("sole author", "Sole Author"),
        ("Sole author and maintainer", "Sole Author and Maintainer"),
        ("  lead\tAPI   engineer  ", "Lead API Engineer"),
        ("iOS and eBay contributor", "iOS and eBay Contributor"),
        ("Node.js and SQLModel maintainer", "Node.js and SQLModel Maintainer"),
        ("AI/ML engineer", "AI/ML Engineer"),
        ("API-based systems lead", "API-based Systems Lead"),
        ("head Of R&D", "Head of R&D"),
        ("mechanical engineering co-op", "Mechanical Engineering Co-op"),
        ("open-source maintainer", "Open-Source Maintainer"),
        ("系统工程师", "系统工程师"),
        ("", ""),
    ],
)
def test_labels_keep_technical_spelling_and_connecting_words(source, expected):
    assert format_label(source) == expected


@pytest.mark.parametrize(
    "source,expected",
    [
        (None, None),
        (" \t ", ""),
        ("2024", "2024"),
        ("2026-03", "Mar 2026"),
        ("2026/3", "Mar 2026"),
        ("  march   2026 ", "Mar 2026"),
        ("Sept. 2022", "Sep 2022"),
        ("September 2022", "Sep 2022"),
        ("2024-02-29", "Feb 29, 2024"),
        ("February 29, 2024", "Feb 29, 2024"),
        ("29 February 2024", "Feb 29, 2024"),
        ("2023-02-29", "2023-02-29"),
        ("2026-13", "2026-13"),
        ("03/04/2026", "03/04/2026"),
        ("Fall 2024", "Fall 2024"),
        ("2026年3月", "2026年3月"),
        ("present", "Present"),
        ("CURRENT", "Present"),
        ("ongoing", "Present"),
    ],
)
def test_dates_preserve_precision_and_do_not_guess_ambiguous_values(source, expected):
    assert format_date(source) == expected


def test_formatted_categories_keep_all_skills_and_source_content():
    content = _mixed_metadata()
    content.skills["AI & Data"] = [TailoredSkill(name="OpenAI", provenance="openai")]
    content.projects[0].description = "Built an API with iOS and eBay integrations."
    content.projects[0].tech = ["Node.js", "SQLModel"]
    original = content.model_dump_json()

    rendered = format_resume_metadata(content)

    assert list(rendered.skills) == ["AI & Data"]
    assert [skill.provenance for skill in rendered.skills["AI & Data"]] == [
        "fastapi",
        "openai",
    ]
    assert rendered.projects[0].name == content.projects[0].name
    assert rendered.projects[0].provenance == content.projects[0].provenance
    assert rendered.projects[0].description == content.projects[0].description
    assert rendered.projects[0].tech == content.projects[0].tech
    assert rendered.contact == content.contact
    assert content.model_dump_json() == original


def test_missing_optional_roles_and_dates_remain_empty():
    content = ResumeContent(
        contact=Contact(name="Alex Sample"),
        projects=[TailoredProject(name="Project", provenance="project")],
        volunteer=[TailoredVolunteer(organization="Club", provenance="volunteer")],
    )
    rendered = format_resume_metadata(content)
    assert rendered.projects[0].role is None
    assert rendered.volunteer[0].role is None
    assert rendered.projects[0].start is None
    assert rendered.projects[0].end is None
