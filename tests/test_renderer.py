import pytest
from pypdf import PdfReader

from resume_tailor_harness.models.profile import Contact, Education
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
    TailoredSkill,
)
from resume_tailor_harness.render.renderer import output_filename, render_pdf


def test_output_filename_slugifies():
    name = output_filename("Acme Corp, Inc.", "Senior Backend Engineer", "20260609")
    assert name == "acme_corp_inc_senior_backend_engineer_20260609.pdf"


def _full_content() -> ResumeContent:
    return ResumeContent(
        contact=Contact(
            name="Ada Lovelace",
            email="ada@example.com",
            location="London, UK",
        ),
        summary="Backend engineer with a focus on reliability.",
        experience=[
            TailoredExperience(
                company="Analytical Engines",
                title="Staff Engineer",
                start="2020",
                end="Present",
                bullets=[
                    TailoredBullet(text="Cut p99 latency by 40%.", provenance="b1")
                ],
                provenance="e1",
            )
        ],
        projects=[
            TailoredProject(
                name="Looms",
                description="A distributed scheduler.",
                tech=["Python", "Rust"],
                bullets=[
                    TailoredBullet(text="Open-sourced; 1k stars.", provenance="p1b1")
                ],
                provenance="p1",
            )
        ],
        skills={"languages": [TailoredSkill(name="Python", provenance="s1")]},
        education=[
            Education(institution="Cambridge", degree="BA", field="Mathematics")
        ],
    )


def test_render_pdf_writes_a_pdf(tmp_path):
    out = tmp_path / "resume.pdf"
    result = render_pdf(_full_content(), out, template_path="templates/resume.typ")
    assert result == out
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize("highlight_terms", [None, [], ["Python", "Python 3", "C++"]])
def test_skills_use_bold_labels_and_regular_names(tmp_path, highlight_terms):
    content = _full_content()
    content.skills = {
        "Languages": [
            TailoredSkill(name="Python 3", provenance="s1"),
            TailoredSkill(name="C++", provenance="s2"),
        ],
        "Tools": [TailoredSkill(name="Docker", provenance="s3")],
    }
    content.experience[0].bullets[0].text = "Built Python services; cut latency 40%."
    out = tmp_path / "skills.pdf"
    render_pdf(
        content,
        out,
        fit_pages=None,
        highlight_terms=highlight_terms,
    )

    spans = []

    def collect(text, cm, tm, font, size):
        if text.strip():
            spans.append((text, str(font.get("/BaseFont", "")) if font else ""))

    page = PdfReader(str(out)).pages[0]
    text = page.extract_text(visitor_text=collect)
    assert "Languages: Python 3, C++" in text
    assert "Tools: Docker" in text

    skills_start = next(i for i, (text, _) in enumerate(spans) if text == "SKILLS")
    skills_spans = spans[skills_start + 1 :]
    for label in ("Languages:", "Tools:"):
        assert any(label in text and "Bold" in font for text, font in skills_spans)
    for name in ("Python 3", "C++", "Docker"):
        matching = [(text, font) for text, font in skills_spans if name in text]
        assert matching, f"Missing skill: {name}"
        assert all("Regular" in font for _, font in matching)

    # Skills styling must not disable the existing emphasis in experience bullets.
    assert any("40%" in text and "Bold" in font for text, font in spans[:skills_start])


def test_project_description_keeps_full_width_with_long_tech_stack(tmp_path):
    out = tmp_path / "resume.pdf"
    content = ResumeContent(
        contact=Contact(name="Ada Lovelace"),
        projects=[
            TailoredProject(
                name=(
                    "Deep Agent — Multi-Agent LLM Platform for Enterprise "
                    "Engineering-Data Analytics"
                ),
                description=(
                    "An agentic AI backend that routes engineering-data requests "
                    "to seven domain subagents."
                ),
                tech=[
                    "Python",
                    "LangGraph",
                    "Elasticsearch",
                    "FastAPI",
                    "OpenAI",
                    "Anthropic Claude",
                    "Jira",
                    "Confluence",
                    "Polarion",
                ],
                provenance="p1",
            )
        ],
    )

    render_pdf(content, out, template_path="templates/resume.typ", fit_pages=None)

    layout = PdfReader(str(out)).pages[0].extract_text(extraction_mode="layout")
    assert "An agentic AI backend" in layout


def test_portfolio_highlighting_does_not_change_extracted_ats_text(tmp_path):
    highlighted = tmp_path / "highlighted.pdf"
    plain = tmp_path / "plain.pdf"

    render_pdf(
        _full_content(),
        highlighted,
        template_path="templates/resume.typ",
        fit_pages=None,
        highlight_terms=["Python"],
    )
    render_pdf(
        _full_content(),
        plain,
        template_path="templates/resume.typ",
        fit_pages=None,
        highlight_terms=[],
    )

    highlighted_text = PdfReader(str(highlighted)).pages[0].extract_text()
    plain_text = PdfReader(str(plain)).pages[0].extract_text()
    assert highlighted_text == plain_text
    assert "Python" in highlighted_text
