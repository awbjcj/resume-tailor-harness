"""Real compiler regressions: extraction, readable fitting, and artifact safety."""

import re

import pytest
from pypdf import PdfReader

from resume_tailor_harness.models.resume import TailoredBullet
from resume_tailor_harness.render import renderer
from resume_tailor_harness.render.sample_content import sample_resume_content
from resume_tailor_harness.render.templates import BUNDLED, resolve_template


def _dense_content(roles=4, bullets=5, projects=3):
    content = sample_resume_content()
    content.summary = None
    content.summary_provenance = []
    role = content.experience[0]
    texts = [
        "Cut p95 latency 40% by redesigning the query planner.",
        "Led a four-person team shipping a billing service.",
        "Built Python and PostgreSQL services with automated recovery, structured monitoring, and documented operational playbooks.",
    ]
    role.bullets = [
        TailoredBullet(text=texts[i % 3], provenance=f"b{i}") for i in range(bullets)
    ]
    content.experience = [role.model_copy(deep=True) for _ in range(roles)]
    project = content.projects[0]
    project.bullets = [
        TailoredBullet(
            text="Built an open-source validation pipeline that checks incoming datasets and reports actionable errors before downstream processing.",
            provenance=f"p{i}",
        )
        for i in range(3)
    ]
    content.projects = [project.model_copy(deep=True) for _ in range(projects)]
    return content


def _text(path):
    return " ".join(page.extract_text() for page in PdfReader(path).pages)


@pytest.mark.parametrize("template_id", BUNDLED)
def test_every_layout_renders_one_readable_page_with_work_and_projects(
    tmp_path, template_id
):
    content = sample_resume_content()
    path = renderer.render_pdf(
        content, tmp_path / "resume.pdf", resolve_template(template_id).path
    )
    reader = PdfReader(path)
    assert len(reader.pages) == 1
    sizes = []

    def collect(text, _cm, _tm, _font, size):
        if text.strip():
            sizes.append(size)

    text = reader.pages[0].extract_text(visitor_text=collect)
    assert min(sizes) >= 10
    normalized = " ".join(text.split())
    for owner in (*content.experience, *content.projects):
        for bullet in owner.bullets:
            assert " ".join(bullet.text.split()) in normalized
    assert "Acme Corp" in text and "Open Data Toolkit" in text


def test_borderline_overflow_fits_in_bounded_probes_without_losing_text(
    tmp_path, monkeypatch
):
    content = _dense_content()
    original = content.model_dump_json()
    natural = renderer.render_pdf(content, tmp_path / "natural.pdf", fit_pages=None)
    assert len(PdfReader(natural).pages) == 2
    compiler_type = renderer.typst.Compiler
    probes = []

    class CountingCompiler:
        def __init__(self, *args, **kwargs):
            self.compiler = compiler_type(*args, **kwargs)

        def compile(self, **kwargs):
            probes.append(kwargs["sys_inputs"])
            return self.compiler.compile(**kwargs)

    monkeypatch.setattr(renderer.typst, "Compiler", CountingCompiler)
    fitted = renderer.render_pdf(content, tmp_path / "fitted.pdf", min_zoom=0.82)
    assert len(PdfReader(fitted).pages) == 1
    assert 2 <= len(probes) <= 5
    assert re.sub(r"\s+", "", _text(fitted)) == re.sub(r"\s+", "", _text(natural))
    assert content.model_dump_json() == original


def test_two_page_mode_compacts_a_sliver_without_adding_or_losing_text(tmp_path):
    content = _dense_content()
    natural = renderer.render_pdf(content, tmp_path / "natural.pdf", fit_pages=None)
    detailed = renderer.render_pdf(content, tmp_path / "detailed.pdf", fit_pages=2)
    assert len(PdfReader(detailed).pages) == 1
    assert renderer._last_page_fill(natural.read_bytes()) < 0.2
    assert renderer._last_page_fill(detailed.read_bytes()) > 0.35
    assert re.sub(r"\s+", "", _text(detailed)) == re.sub(r"\s+", "", _text(natural))


@pytest.mark.parametrize("template_id", BUNDLED)
def test_longer_content_fits_within_two_pages_in_every_layout(tmp_path, template_id):
    path = renderer.render_pdf(
        _dense_content(roles=5, bullets=7, projects=4),
        tmp_path / "detailed.pdf",
        resolve_template(template_id).path,
        fit_pages=2,
    )
    assert len(PdfReader(path).pages) == 2
    assert min(renderer._page_fills(path.read_bytes())) >= renderer.MIN_PAGE_FILL


@pytest.mark.parametrize("template_id", BUNDLED)
def test_half_page_tail_expands_without_content_loss_or_unreadable_type(
    tmp_path, template_id
):
    content = _dense_content(roles=5, bullets=7, projects=4)
    original = content.model_dump_json()
    natural = renderer.render_pdf(
        content, tmp_path / "natural.pdf", BUNDLED[template_id].path, fit_pages=None
    )
    fitted = renderer.render_pdf(
        content, tmp_path / "fitted.pdf", BUNDLED[template_id].path, fit_pages=2
    )
    assert min(renderer._page_fills(fitted.read_bytes())) >= renderer.MIN_PAGE_FILL
    assert re.sub(r"\s+", "", _text(fitted)) == re.sub(r"\s+", "", _text(natural))
    assert content.model_dump_json() == original
    sizes = []
    for page in PdfReader(fitted).pages:
        page.extract_text(
            visitor_text=lambda text, cm, tm, font, size: (
                sizes.append(size) if text.strip() else None
            )
        )
    assert min(sizes) >= 10 and max(size for size in sizes if size < 20) <= 12


def test_unbalanced_content_requests_revision_and_keeps_previous_artifact(tmp_path):
    path = tmp_path / "previous.pdf"
    path.write_bytes(b"previous validated artifact")
    with pytest.raises(renderer.PageBalanceError, match="verified"):
        renderer.render_pdf(
            _dense_content(roles=5, bullets=6, projects=3), path, fit_pages=2
        )
    assert path.read_bytes() == b"previous validated artifact"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("target", [1, 2])
def test_impossible_fit_preserves_existing_pdf_and_source_content(tmp_path, target):
    content = _dense_content(roles=12, bullets=10, projects=10)
    original = content.model_dump_json()
    path = tmp_path / "existing.pdf"
    path.write_bytes(b"previous validated artifact")
    with pytest.raises(
        renderer.PageFitError, match="Shorten repeated wording"
    ) as error:
        renderer.render_pdf(content, path, fit_pages=target)
    assert error.value.pages > target
    assert path.read_bytes() == b"previous validated artifact"
    assert content.model_dump_json() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("step", [0, -0.1, float("nan")])
def test_invalid_fit_step_fails_before_compilation(tmp_path, step):
    with pytest.raises(ValueError, match="zoom_step"):
        renderer.render_pdf(sample_resume_content(), tmp_path / "x.pdf", zoom_step=step)


def test_section_order_hint_preserves_omitted_populated_sections(tmp_path):
    content = sample_resume_content()
    content.section_order = ["projects", "experience"]
    path = renderer.render_pdf(content, tmp_path / "resume.pdf")
    text = _text(path)
    assert text.index("PROJECTS") < text.index("PROFESSIONAL EXPERIENCE")
    assert "SKILLS" in text and "EDUCATION" in text


@pytest.mark.parametrize(
    "template_id,first", [("graduate", "EDUCATION"), ("academic", "Education")]
)
def test_education_first_layout_defaults(tmp_path, template_id, first):
    path = renderer.render_pdf(
        sample_resume_content(), tmp_path / "resume.pdf", BUNDLED[template_id].path
    )
    text = _text(path)
    assert text.index(first) < text.lower().index("professional experience")


def test_current_role_dates_have_present_and_no_null_text(tmp_path):
    content = sample_resume_content()
    content.experience[0].end = None
    path = renderer.render_pdf(content, tmp_path / "resume.pdf")
    assert "2021 – Present" in _text(path)
    assert "none" not in _text(path)


@pytest.mark.parametrize("template_id", ["modern", "technical", "minimal"])
def test_sans_serif_layout_uses_bundled_fonts_without_system_fonts(
    tmp_path, monkeypatch, template_id
):
    compiler_type = renderer.typst.Compiler

    def isolated_compiler(*args, **kwargs):
        return compiler_type(*args, **kwargs, ignore_system_fonts=True)

    monkeypatch.setattr(renderer.typst, "Compiler", isolated_compiler)
    path = renderer.render_pdf(
        sample_resume_content(), tmp_path / "resume.pdf", BUNDLED[template_id].path
    )
    fonts = []

    def collect(text, _cm, _tm, font, _size):
        if text.strip() and font:
            fonts.append(str(font.get("/BaseFont", "")))

    PdfReader(path).pages[0].extract_text(visitor_text=collect)
    assert fonts and all("SourceSans3" in font for font in fonts)
