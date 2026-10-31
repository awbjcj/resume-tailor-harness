from pypdf import PdfReader
import pytest

from resume_tailor_harness.models.profile import (
    AdditionalEntry,
    AdditionalSection,
    Contact,
    Education,
    Language,
)
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredAward,
    TailoredBullet,
    TailoredCertification,
    TailoredExperience,
    TailoredPublication,
    TailoredProject,
    TailoredVolunteer,
)
from resume_tailor_harness.render.renderer import render_pdf
from resume_tailor_harness.render.templates import BUNDLED


def _rich_content() -> ResumeContent:
    return ResumeContent(
        contact=Contact(
            name="Jiajin Wu", email="x@example.com", location="Ann Arbor, MI"
        ),
        summary="Vehicle systems engineer.",
        experience=[
            TailoredExperience(
                company="Aptiv",
                title="Triage Engineer",
                start="2023",
                end="Present",
                location="Troy, MI",
                provenance="e1",
                bullets=[
                    TailoredBullet(text="Triaged L1-L3 ADAS issues", provenance="b1")
                ],
            )
        ],
        education=[
            Education(
                institution="U-Mich",
                degree="M.Eng",
                field="Systems",
                end="2022",
                gpa="3.9",
                honors=["Dean's List"],
                activities=["Engineering Society"],
            )
        ],
        publications=[
            TailoredPublication(
                title="On ADAS Triage",
                venue="SAE",
                date="2022",
                provenance="pub1",
                authors=["Jiajin Wu", "Alex Researcher"],
                url="https://example.com/paper",
            )
        ],
        certifications=[
            TailoredCertification(
                name="Six Sigma",
                issuer="ASQ",
                provenance="cer1",
                credential_id="ABC-123",
                url="https://example.com/credential",
            )
        ],
        awards=[TailoredAward(name="Best Intern", provenance="awa1")],
        portfolio=[
            TailoredProject(
                name="Control Case Study",
                provenance="p1",
                url="https://example.com/portfolio",
                role="Engineer",
            )
        ],
        interests=["Robotics outreach"],
        additional_sections=[
            AdditionalSection(
                title="Teaching",
                entries=[
                    AdditionalEntry(
                        title="Systems Lab",
                        organization="U-Mich",
                        date="2022",
                        description="Taught laboratory sessions.",
                    )
                ],
            )
        ],
        languages=[Language(language="English", proficiency="native")],
        volunteer=[
            TailoredVolunteer(
                organization="Robotics Club",
                role="Mentor",
                provenance="vol1",
                bullets=[
                    TailoredBullet(text="Coached FIRST teams", provenance="volb1")
                ],
            )
        ],
        section_order=[
            "summary",
            "experience",
            "education",
            "publications",
            "certifications",
            "awards",
            "languages",
            "volunteer",
        ],
    )


def _text_of(pdf_path) -> str:
    return "\n".join(
        (page.extract_text() or "") for page in PdfReader(str(pdf_path)).pages
    )


@pytest.mark.parametrize("template_id", BUNDLED)
def test_template_renders_all_new_sections(tmp_path, template_id):
    out = tmp_path / "rich.pdf"
    render_pdf(_rich_content(), out, template_path=BUNDLED[template_id].path)
    assert out.read_bytes().startswith(b"%PDF")
    text = _text_of(out)
    for needle in [
        "PUBLICATIONS",
        "CERTIFICATIONS",
        "AWARDS",
        "LANGUAGES",
        "EDUCATION",
        "VOLUNTEER",
        "3.9",
        "Six Sigma",
        "Robotics Club",
        "Summary",
        "Honors & Awards",
        "Portfolio",
        "Control Case Study",
        "Teaching",
        "Systems Lab",
        "Engineering Society",
        "Jiajin Wu, Alex Researcher",
        "ABC-123",
        "Robotics outreach",
    ]:
        assert needle.lower() in text.lower(), f"missing {needle!r} in rendered PDF"
    urls = {
        annotation.get_object()["/A"].get("/URI")
        for page in PdfReader(out).pages
        for annotation in page.get("/Annots", [])
        if "/A" in annotation.get_object()
    }
    assert {
        "https://example.com/paper",
        "https://example.com/credential",
        "https://example.com/portfolio",
    } <= urls


@pytest.mark.parametrize("template_id", BUNDLED)
def test_empty_optional_sections_have_no_headings(tmp_path, template_id):
    path = render_pdf(
        ResumeContent(contact=Contact(name="Alex")),
        tmp_path / "empty.pdf",
        BUNDLED[template_id].path,
    )
    assert _text_of(path).strip() == "Alex"
