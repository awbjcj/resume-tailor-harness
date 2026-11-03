"""Measure actual PDF glyphs so fitting cannot erase entry/metadata gaps."""

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader

from resume_tailor_harness.models.profile import Education, Link
from resume_tailor_harness.models.resume import TailoredProject
from resume_tailor_harness.render.layout_review import _PDFIUM_LOCK
from resume_tailor_harness.render.renderer import render_pdf
from resume_tailor_harness.render.sample_content import sample_resume_content
from resume_tailor_harness.render.templates import BUNDLED


def _typography_content():
    content = sample_resume_content()
    content.summary = None
    content.summary_provenance = []
    content.contact.links = [Link(label="Portfolio", url="https://example.com/alex")]
    content.experience = content.experience[:1]
    content.experience[0].bullets = content.experience[0].bullets[:1]
    content.experience[0].location = "New York, NY"
    content.projects = content.projects[:1]
    project = content.projects[0]
    # Deliberately no role or URL: the title must still clear the tech stack.
    project.description = "A validation platform for engineering datasets."
    project.tech = [
        "Python",
        "SQL",
        "Docker",
        "TypeScript",
        "PostgreSQL",
        "Elasticsearch",
        "FastAPI",
        "LangGraph",
        "GitHub Actions",
        "OpenTelemetry",
        "Kubernetes",
        "Linux",
        "Prometheus",
        "Grafana",
        "Redis",
    ]
    project.bullets = project.bullets[:1]
    content.portfolio = [
        TailoredProject(
            name="Engineering Case Study",
            role="Lead Engineer",
            url="https://example.com/case-study",
            tech=["Rust", "REST APIs"],
            description="A service integration case study.",
            provenance="sample-portfolio",
        )
    ]
    content.education = [
        Education(
            institution="State University",
            degree="BSc",
            field="Computer Science",
            gpa="3.9",
            relevant_coursework=["Distributed Systems", "Data Engineering"],
            activities=["Engineering Society"],
        )
    ]
    return content


def _bounds(textpage, needle):
    search = textpage.search(needle)
    try:
        match = search.get_next()
        assert match is not None, f"Missing PDF text: {needle}"
        index, count = match
        boxes = [
            textpage.get_charbox(i)
            for i in range(index, index + count)
            if textpage.get_text_range(i, 1).strip()
        ]
        return (
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        )
    finally:
        search.close()


@pytest.mark.parametrize("template_id", BUNDLED)
@pytest.mark.parametrize("density", [-1, 0, 1])
def test_readable_gaps_survive_every_template_and_density(
    tmp_path, template_id, density
):
    content = _typography_content()
    content.layout_density = density
    path = render_pdf(
        content, tmp_path / "spacing.pdf", BUNDLED[template_id].path, fit_pages=None
    )
    assert len(PdfReader(path).pages) == 1
    project = content.projects[0]
    # PDFium uses bottom-up coordinates. Compare visible ink, including the
    # last wrapped line, rather than template constants or PDF font boxes.
    with _PDFIUM_LOCK, pdfium.PdfDocument(path) as document:
        page = document[0]
        textpage = page.get_textpage()
        try:
            for upper, lower in [
                ("Acme Corp", "Senior Engineer"),
                ("Senior Engineer", "Cut p95 latency"),
                (project.name, " · ".join(project.tech)),
                (" · ".join(project.tech), project.description),
                (project.description, "Built an open-source"),
                ("Engineering Case Study", "Lead Engineer"),
                ("Lead Engineer", "https://example.com/case-study"),
                ("https://example.com/case-study", "Rust · REST APIs"),
                ("Rust · REST APIs", "A service integration case study."),
                (
                    "Hard skills: Python, PostgreSQL, SQL, TypeScript",
                    "Engineering: API design",
                ),
                ("GPA: 3.9", "Coursework: Distributed Systems"),
                (
                    "Coursework: Distributed Systems, Data Engineering",
                    "Activities: Engineering Society",
                ),
            ]:
                gap = _bounds(textpage, upper)[1] - _bounds(textpage, lower)[3]
                assert gap >= 3, (
                    f"{upper!r} -> {lower!r}: only {gap:.2f}pt of visible space"
                )
        finally:
            textpage.close()
            page.close()


@pytest.mark.parametrize("template_id", BUNDLED)
def test_wrapped_titles_and_metadata_keep_content_width_and_links(
    tmp_path, template_id
):
    content = _typography_content()
    project = content.projects[0]
    project.name = "Deep Agent - Multi-Agent Platform for Enterprise Engineering Data Analytics and Operations"
    project.role = "Platform Engineer and Maintainer"
    project.start, project.end = "2024", "Present"
    project.url = "https://example.com/engineering-data-platform"
    project.repo_url = "https://github.com/example/engineering-data-platform"
    content.experience[
        0
    ].title = (
        "Senior Software Engineer for Platform Reliability and Developer Experience"
    )
    content.layout_density = 1
    path = render_pdf(
        content, tmp_path / "wrapped.pdf", BUNDLED[template_id].path, fit_pages=None
    )
    with _PDFIUM_LOCK, pdfium.PdfDocument(path) as document:
        page = document[0]
        textpage = page.get_textpage()
        try:
            title = _bounds(textpage, project.name)
            role = _bounds(textpage, project.role)
            assert title[1] - role[3] >= 3
            description = _bounds(textpage, project.description)
            assert description[0] == pytest.approx(0.6 * 72, abs=1)
            assert _bounds(textpage, " · ".join(project.tech))[1] - description[3] >= 3
        finally:
            textpage.close()
            page.close()
    urls = {
        annotation.get_object()["/A"].get("/URI")
        for page in PdfReader(path).pages
        for annotation in page.get("/Annots", [])
        if "/A" in annotation.get_object()
    }
    assert {project.url, project.repo_url} <= urls


@pytest.mark.parametrize("bullet_count", [14, 15, 16, 17])
def test_short_project_does_not_leave_a_single_bullet_on_the_next_page(
    tmp_path, bullet_count
):
    content = sample_resume_content()
    content.summary = None
    content.summary_provenance = []
    content.skills = {}
    content.education = []
    content.experience = content.experience[:1]
    role = content.experience[0]
    role.bullets = [role.bullets[0].model_copy(deep=True) for _ in range(bullet_count)]
    content.projects = content.projects[:1]
    project = content.projects[0]
    project.bullets = project.bullets[:2]
    path = render_pdf(content, tmp_path / "page-break.pdf", fit_pages=None)
    pages = [" ".join(page.extract_text().split()) for page in PdfReader(path).pages]
    project_page = next(page for page in pages if project.name in page)
    for bullet in project.bullets:
        assert " ".join(bullet.text.split()) in project_page
