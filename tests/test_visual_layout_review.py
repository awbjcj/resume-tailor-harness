"""Rendered evidence delivery and the bounded review/revise loop, without providers."""

import asyncio
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError
from pypdf import PdfReader

from resume_tailor_harness.llm_runner import AgentRunner
from resume_tailor_harness.models.job import JobCriteria
from resume_tailor_harness.models.profile import (
    Bullet,
    Contact,
    Experience,
    ProfileFacts,
)
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredBullet,
    TailoredExperience,
)
from resume_tailor_harness.models.review import (
    MergedPanelReview,
    ReviewCritique,
    ReviewIssue,
    Severity,
)
from resume_tailor_harness.render import layout_review
from resume_tailor_harness.render.layout_review import render_layout_preview
from resume_tailor_harness.render.render_config import RenderConfig
from resume_tailor_harness.render.renderer import render_pdf
from resume_tailor_harness.render.sample_content import sample_resume_content
from resume_tailor_harness.tailor.panel import MERGED_ADVISORY, arun_panel, run_panel
from resume_tailor_harness.tailor.review_config import ReviewConfig, ReviewerSpec
from resume_tailor_harness.tailor.verdict import aggregate, failing_gate_names
from resume_tailor_harness.tailor.workflow import arun_tailor_review, run_tailor_review


class TextAgent:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def run(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(
            content=self.outputs[min(len(self.prompts) - 1, len(self.outputs) - 1)]
        )

    async def arun(self, prompt):
        return self.run(prompt)


class VisionAgent(TextAgent):
    def __init__(self, *outputs):
        super().__init__(*outputs)
        self.images = []

    def run_images(self, prompt, images):
        self.images.append(images)
        return self.run(prompt)

    async def arun_images(self, prompt, images):
        return self.run_images(prompt, images)


def critique(name="concision", passed=True):
    return ReviewCritique(
        reviewer=name,
        passed=passed,
        score=100 if passed else 30,
        issues=[]
        if passed
        else [
            ReviewIssue(
                severity=Severity.major,
                location="page 1 summary",
                message="Opening text is crowded.",
                suggestion="Lower layout_density to -0.5 and preserve the role-fit summary.",
            )
        ],
    )


def content_and_facts():
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        experience=[
            Experience(
                id="e1",
                company="AE",
                title="Engineer",
                bullets=[Bullet(id="b1", text="Built Python services")],
            )
        ],
    )
    content = ResumeContent(
        contact=facts.contact,
        summary="Python engineer who built services relevant to the backend role.",
        summary_provenance=["b1"],
        experience=[
            TailoredExperience(
                company="AE",
                title="Engineer",
                provenance="e1",
                bullets=[TailoredBullet(text="Built Python services", provenance="b1")],
            )
        ],
    )
    return content, facts


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("merged", [False, True])
@pytest.mark.parametrize("format_gate", [False, True])
def test_only_format_reviewer_receives_real_images(asynchronous, merged, format_gate):
    content, facts = content_and_facts()
    config = ReviewConfig(
        merged_advisory=merged,
        reviewers=[
            ReviewerSpec(name="fact-check", gate=True),
            ReviewerSpec(name="concision", gate=format_gate),
            ReviewerSpec(name="recruiter"),
        ],
    )
    fact_check = TextAgent(critique("fact-check"))
    format_review = VisionAgent(critique())
    merged_output = (
        [critique("recruiter")] if format_gate else [critique(), critique("recruiter")]
    )
    advisory = (
        VisionAgent(MergedPanelReview(critiques=merged_output))
        if merged
        else TextAgent(critique("recruiter"))
    )
    agents = {
        "fact-check": fact_check,
        "concision": format_review,
        MERGED_ADVISORY if merged else "recruiter": advisory,
    }
    render_config = RenderConfig(template="modern")
    if asynchronous:

        async def go():
            return await arun_panel(
                content,
                facts,
                "Python backend role",
                config,
                agents,
                sem=asyncio.Semaphore(2),
                render_config=render_config,
            )

        reviews = asyncio.run(go())
    else:
        reviews = run_panel(
            content,
            facts,
            "Python backend role",
            config,
            agents,
            render_config=render_config,
        )
    visual = advisory if merged and not format_gate else format_review
    assert isinstance(visual, VisionAgent)
    assert visual.images and visual.images[0][0].startswith(b"\x89PNG")
    with Image.open(io.BytesIO(visual.images[0][0])) as page:
        assert max(page.size) <= layout_review.MAX_IMAGE_EDGE
        assert min(page.size) > 1000  # full-page text remains legible
    assert "RENDERED LAYOUT EVIDENCE" in visual.prompts[0]
    if not format_gate:
        assert "16 bullets in total" in visual.prompts[0]
    assert "SUPPORTING FACTS" in fact_check.prompts[0]
    assert "RENDERED LAYOUT" not in fact_check.prompts[0]
    assert {r.reviewer for r in reviews} == {
        "layout-fit",
        "concision",
        "recruiter",
        "fact-check",
    }
    assert aggregate(reviews, config).passed


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("bad_revision", [False, True])
def test_revision_renders_new_pages_and_rechecks_facts(asynchronous, bad_revision):
    content, facts = content_and_facts()
    revised = content.model_copy(deep=True)
    revised.layout_density = -0.5
    if bad_revision:
        revised.summary_provenance = ["missing-fact"]
    writer, reviser = TextAgent(content), TextAgent(revised)
    reviewer = VisionAgent(critique(passed=False), critique())
    config = ReviewConfig(
        max_rounds=2,
        provenance_retry_budget=0,
        reviewers=[ReviewerSpec(name="concision")],
    )
    args = (
        "Python backend role",
        JobCriteria(),
        facts,
        config,
        writer,
        {"concision": reviewer},
        reviser,
    )
    if asynchronous:

        async def go():
            return await arun_tailor_review(
                *args, sem=asyncio.Semaphore(2), render_config=RenderConfig()
            )

        rounds = asyncio.run(go())
    else:
        rounds = run_tailor_review(*args, render_config=RenderConfig())
    assert len(rounds) == 2
    assert "page 1 summary" in reviser.prompts[0]
    assert "Lower layout_density" in reviser.prompts[0]
    assert "16 bullets in total" in writer.prompts[0]
    assert "16 bullets in total" in reviser.prompts[0]
    assert reviewer.images[0] != reviewer.images[1]
    assert rounds[-1].content.layout_density == -0.5
    assert rounds[-1].content.summary == content.summary
    assert rounds[-1].verdict.passed is (not bad_revision)
    assert all(
        any(c.reviewer == "layout-fit" for c in r.verdict.critiques) for r in rounds
    )
    if bad_revision:
        assert "provenance" in failing_gate_names(rounds[-1].verdict.critiques)


def test_overflow_is_diagnostic_and_bounded_and_temp_pdf_is_removed(
    tmp_path, monkeypatch
):
    template = tmp_path / "six-pages.typ"
    template.write_text(
        "#set page(width: 8.5in, height: 11in)\n"
        + "\n#pagebreak()\n".join(f"Page {i}" for i in range(1, 7)),
        encoding="utf-8",
    )
    paths = []
    original = layout_review.render_pdf

    def capture(*args, **kwargs):
        paths.append(Path(args[1]))
        return original(*args, **kwargs)

    monkeypatch.setattr(layout_review, "render_pdf", capture)
    preview = render_layout_preview(
        ResumeContent(contact=Contact(name="Ada")),
        RenderConfig(template_path=str(template)),
    )
    assert preview.page_count == 6
    assert preview.page_numbers == (1, 2, 3, 6)
    assert len(preview.images) == 4
    assert "unconstrained draft" in preview.prompt()
    assert not preview.critique().passed
    assert all(not path.parent.exists() for path in paths)
    verdict = aggregate(
        [preview.critique(), critique()],
        ReviewConfig(reviewers=[ReviewerSpec(name="concision")]),
    )
    assert verdict.aggregate_score == 100 and not verdict.passed
    assert failing_gate_names(verdict.critiques, []) == ["layout-fit"]


@pytest.mark.parametrize("asynchronous", [False, True])
def test_text_only_adapter_cannot_claim_visual_review(asynchronous):
    content, facts = content_and_facts()
    agent = TextAgent(critique())
    config = ReviewConfig(reviewers=[ReviewerSpec(name="concision")])
    with pytest.raises(TypeError, match="image-capable"):
        if asynchronous:

            async def go():
                return await arun_panel(
                    content,
                    facts,
                    "JD",
                    config,
                    {"concision": agent},
                    sem=asyncio.Semaphore(1),
                    render_config=RenderConfig(),
                )

            asyncio.run(go())
        else:
            run_panel(
                content,
                facts,
                "JD",
                config,
                {"concision": agent},
                render_config=RenderConfig(),
            )
    assert not agent.prompts


@pytest.mark.parametrize("density,expected_size", [(-1, 12), (0, 10.5), (1, 10)])
def test_export_honors_bounded_layout_preference_without_content_loss(
    tmp_path, density, expected_size
):
    content = sample_resume_content()
    content.layout_density = density
    path = render_pdf(content, tmp_path / "resume.pdf", fit_pages=None)
    sizes = []

    def collect(text, _cm, _tm, _font, size):
        if "query planner" in text:
            sizes.append(size)

    text = " ".join(p.extract_text(visitor_text=collect) for p in PdfReader(path).pages)
    assert content.summary is not None and content.summary in " ".join(text.split())
    assert sizes and all(
        size == pytest.approx(expected_size, abs=0.01) for size in sizes
    )


@pytest.mark.parametrize("density", [-1.1, 1.1, float("nan"), float("inf")])
def test_invalid_density_is_rejected(density):
    with pytest.raises(ValidationError):
        ResumeContent(contact=Contact(name="Ada"), layout_density=density)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_agent_runner_passes_images_through_retry_and_usage(monkeypatch, asynchronous):
    import resume_tailor_harness.llm_runner as llm
    from resume_tailor_harness.config import Settings

    recorded = []

    class Retry(Exception):
        status_code = 429

    class Provider:
        def __init__(self):
            self.received = []

        def run(self, prompt, *, images):
            self.received.append((prompt, images))
            if len(self.received) == 1:
                raise Retry()
            return "ok"

        async def arun(self, prompt, *, images):
            return self.run(prompt, images=images)

    monkeypatch.setattr(llm, "record_call", lambda a, r: recorded.append(r))
    provider = Provider()
    runner = AgentRunner(provider, settings=Settings(llm_retries=1, llm_retry_delay=0))
    images = (b"png-page-one", b"png-page-two")
    result = (
        asyncio.run(runner.arun_images("review", images))
        if asynchronous
        else runner.run_images("review", images)
    )
    assert result == "ok" and recorded == ["ok"]
    assert len(provider.received) == 2
    for prompt, supplied in provider.received:
        assert prompt == "review"
        assert tuple(image.content for image in supplied) == images
        assert all(image.mime_type == "image/png" for image in supplied)


def test_preview_rejects_oversized_pdf_without_retaining_it(tmp_path, monkeypatch):
    paths = []

    def oversized(_content, path, *_args, **_kwargs):
        paths.append(path)
        path.write_bytes(b"oversized")
        return path

    monkeypatch.setattr(layout_review, "render_pdf", oversized)
    monkeypatch.setattr(layout_review, "MAX_PREVIEW_BYTES", 2)
    with pytest.raises(ValueError, match="byte limit"):
        render_layout_preview(
            ResumeContent(contact=Contact(name="Ada")), RenderConfig()
        )
    assert paths and not paths[0].parent.exists()


def test_cancelled_render_keeps_permit_until_cleanup_and_never_calls_provider(
    monkeypatch,
):
    import threading
    import resume_tailor_harness.tailor.panel as panel

    started, release = threading.Event(), threading.Event()
    content, facts = content_and_facts()
    reviewer = VisionAgent(critique())
    config = ReviewConfig(reviewers=[ReviewerSpec(name="concision")])

    def slow_preview(*_args, **_kwargs):
        started.set()
        assert release.wait(timeout=5)
        return None

    monkeypatch.setattr(panel, "render_layout_preview", slow_preview)

    async def go():
        sem = asyncio.Semaphore(1)
        task = asyncio.create_task(
            arun_panel(
                content,
                facts,
                "JD",
                config,
                {"concision": reviewer},
                sem=sem,
                render_config=RenderConfig(),
            )
        )
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert sem.locked() and not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not sem.locked()

    asyncio.run(go())
    assert not reviewer.prompts


def test_provider_image_rejection_surfaces_without_text_fallback():
    class RejectImages:
        def run(self, _prompt, **_kwargs):
            raise ValueError("model does not support images")

        async def arun(self, prompt, **kwargs):
            return self.run(prompt, **kwargs)

    content, facts = content_and_facts()
    with pytest.raises(ValueError, match="does not support images"):
        run_panel(
            content,
            facts,
            "JD",
            ReviewConfig(reviewers=[ReviewerSpec(name="concision")]),
            {"concision": AgentRunner(RejectImages())},
            render_config=RenderConfig(),
        )


def test_summary_fit_rule_reaches_writers_and_both_panel_modes():
    from resume_tailor_harness.tailor.agents import (
        _TAILOR_INSTRUCTIONS,
        _REVISER_INSTRUCTIONS,
        _writer_instructions,
        _reviewer_instructions,
        _merged_advisory_instructions,
    )

    for base in (_TAILOR_INSTRUCTIONS, _REVISER_INSTRUCTIONS):
        prompt = " ".join(_writer_instructions(base))
        assert "why the candidate is a good fit" in prompt
        assert "highest-priority responsibilities" in prompt
        assert "summary_provenance" in prompt
    for instructions in (
        _reviewer_instructions("recruiter"),
        _merged_advisory_instructions(["recruiter", "concision"]),
    ):
        assert "requirement-to-evidence connection" in " ".join(instructions)
