import asyncio
import json
from collections.abc import Coroutine, Mapping
from typing import Any

from resume_tailor_harness.llm_runner import (
    Runner,
    acall,
    call_with_images,
    expect_schema,
)
from resume_tailor_harness.models.profile import ProfileFacts
from resume_tailor_harness.models.resume import ResumeContent
from resume_tailor_harness.models.review import MergedPanelReview, ReviewCritique
from resume_tailor_harness.render.layout_review import (
    LayoutPreview,
    render_layout_preview,
)
from resume_tailor_harness.render.render_config import RenderConfig
from resume_tailor_harness.tailor.length import (
    format_budget,
    format_depth_plan,
    resume_stats,
)
from resume_tailor_harness.tailor.prompt_blocks import coverage_section, untrusted
from resume_tailor_harness.tailor.provenance import resolve_evidence
from resume_tailor_harness.tailor.review_config import ReviewConfig

MERGED_ADVISORY = "advisory-panel"


def split_merged_critiques(
    review: MergedPanelReview, expected: list[str]
) -> list[ReviewCritique]:
    """Require exact unique coverage, then restore configured reviewer order."""
    received = [critique.reviewer for critique in review.critiques]
    if len(received) != len(set(received)) or sorted(received) != sorted(expected):
        raise ValueError(
            f"Merged advisory review must cover exactly {expected!r}, got {received!r}"
        )
    by_name = {critique.reviewer: critique for critique in review.critiques}
    return [by_name[name] for name in expected]


def compose_lean_review_input(
    content: ResumeContent,
    jd_text: str,
    stats: str,
    coverage: str = "",
    depth_plan: str = "",
) -> str:
    """Input for reviewers needing no cited evidence: resume + JD + size stats."""
    return (
        "JOB DESCRIPTION:\n"
        f"{untrusted(jd_text)}"
        f"{coverage_section(coverage)}"
        f"{f'\n\n{depth_plan}' if depth_plan else ''}\n\n"
        "RESUME UNDER REVIEW (JSON):\n"
        f"{content.model_dump_json()}\n\n"
        "RESUME STATS:\n"
        f"{stats}"
    )


def compose_evidence_review_input(
    content: ResumeContent, jd_text: str, evidence: Mapping[str, Any]
) -> str:
    """Input for gates and fact-check in either mode: resume + JD + cited facts."""
    return (
        "JOB DESCRIPTION:\n"
        f"{untrusted(jd_text)}\n\n"
        "RESUME UNDER REVIEW (JSON):\n"
        f"{content.model_dump_json()}\n\n"
        "SUPPORTING FACTS (the only profile facts this resume cites, keyed by id):\n"
        f"{json.dumps(evidence)}"
    )


def _validate_reviewer_identity(
    critique: ReviewCritique, expected_reviewer: str | None
) -> ReviewCritique:
    if expected_reviewer is not None and critique.reviewer != expected_reviewer:
        raise ValueError(
            "Reviewer output identity mismatch: "
            f"expected {expected_reviewer!r}, got {critique.reviewer!r}"
        )
    return critique


def review_one(
    input_text: str,
    agent: Runner,
    *,
    expected_reviewer: str | None = None,
    layout: LayoutPreview | None = None,
) -> ReviewCritique:
    critique = expect_schema(
        call_with_images(
            agent,
            input_text + (layout.prompt() if layout else ""),
            layout.images if layout else (),
        ),
        ReviewCritique,
        source="reviewer",
    )
    return _validate_reviewer_identity(critique, expected_reviewer)


def run_panel(
    content: ResumeContent,
    profile_facts: ProfileFacts,
    jd_text: str,
    config: ReviewConfig,
    reviewer_agents: Mapping[str, Runner],
    *,
    coverage: str = "",
    render_config: RenderConfig | None = None,
    highlight_terms: list[str] | None = None,
) -> list[ReviewCritique]:
    """Run configured reviewers with the smallest sufficient input per role."""
    budget = config.length_budget.for_pages(
        (1 if render_config.fit_one_page else 2) if render_config else None
    )
    depth_plan = (
        f"LENGTH BUDGET:\n{format_budget(budget)}\n\n"
        f"{format_depth_plan(profile_facts, budget)}"
    )
    layout = (
        render_layout_preview(content, render_config, highlight_terms=highlight_terms)
        if render_config
        else None
    )
    measurements = [layout.critique()] if layout else []
    if not config.merged_advisory:
        return measurements + [
            review_one(
                text,
                reviewer_agents[name],
                expected_reviewer=name,
                layout=layout if name == "concision" else None,
            )
            for name, text in _panel_inputs(
                content,
                profile_facts,
                jd_text,
                config,
                coverage=coverage,
                depth_plan=depth_plan,
            )
        ]

    evidence = resolve_evidence(content, profile_facts)
    critiques = measurements + [
        review_one(
            compose_evidence_review_input(content, jd_text, evidence),
            reviewer_agents[spec.name],
            expected_reviewer=spec.name,
            layout=layout if spec.name == "concision" else None,
        )
        for spec in config.reviewers
        if spec.requires_evidence
    ]
    advisory_names = _advisory_names(config)
    if advisory_names:
        visual = layout if "concision" in advisory_names else None
        result = call_with_images(
            reviewer_agents[MERGED_ADVISORY],
            compose_lean_review_input(
                content,
                jd_text,
                resume_stats(content),
                coverage=coverage,
                depth_plan=depth_plan,
            )
            + (visual.prompt() if visual else ""),
            visual.images if visual else (),
        )
        critiques.extend(_merged_review(result, advisory_names))
    return critiques


def _advisory_names(config: ReviewConfig) -> list[str]:
    """Only reviewers that can use lean input join the merged advisory call."""
    return [spec.name for spec in config.reviewers if not spec.requires_evidence]


def _merged_review(result: Any, expected: list[str]) -> list[ReviewCritique]:
    """Takes the whole run result, not just its content, so a parse failure can
    report the provider diagnostics that say why it did not parse."""
    review = expect_schema(result, MergedPanelReview, source="merged advisory")
    return split_merged_critiques(review, expected)


def _panel_inputs(
    content: ResumeContent,
    profile_facts: ProfileFacts,
    jd_text: str,
    config: ReviewConfig,
    *,
    coverage: str = "",
    depth_plan: str,
) -> list[tuple[str, str]]:
    """(reviewer_name, input_text) pairs, smallest sufficient input per role."""
    evidence = resolve_evidence(content, profile_facts)
    stats = resume_stats(content)
    inputs: list[tuple[str, str]] = []
    for spec in config.reviewers:
        if spec.requires_evidence:
            text = compose_evidence_review_input(content, jd_text, evidence)
        else:
            text = compose_lean_review_input(
                content, jd_text, stats, coverage=coverage, depth_plan=depth_plan
            )
        inputs.append((spec.name, text))
    return inputs


async def areview_one(
    input_text: str,
    agent: Runner,
    *,
    sem: asyncio.Semaphore,
    expected_reviewer: str | None = None,
    layout: LayoutPreview | None = None,
) -> ReviewCritique:
    result = await acall(
        agent,
        input_text + (layout.prompt() if layout else ""),
        sem=sem,
        images=layout.images if layout else (),
    )
    critique = expect_schema(result, ReviewCritique, source="reviewer")
    return _validate_reviewer_identity(critique, expected_reviewer)


async def arun_panel(
    content: ResumeContent,
    profile_facts: ProfileFacts,
    jd_text: str,
    config: ReviewConfig,
    reviewer_agents: Mapping[str, Runner],
    *,
    sem: asyncio.Semaphore,
    coverage: str = "",
    render_config: RenderConfig | None = None,
    highlight_terms: list[str] | None = None,
) -> list[ReviewCritique]:
    """Run configured reviewers concurrently; results stay in reviewer order."""
    budget = config.length_budget.for_pages(
        (1 if render_config.fit_one_page else 2) if render_config else None
    )
    depth_plan = (
        f"LENGTH BUDGET:\n{format_budget(budget)}\n\n"
        f"{format_depth_plan(profile_facts, budget)}"
    )
    layout = None
    if render_config is not None:
        # Bound CPU/raster work with the same batch limit as provider calls;
        # keep it off the event loop and preserve the active tenant context.
        async with sem:
            rendering = asyncio.create_task(
                asyncio.to_thread(
                    render_layout_preview,
                    content,
                    render_config,
                    highlight_terms=highlight_terms,
                )
            )
            try:
                layout = await asyncio.shield(rendering)
            except asyncio.CancelledError:
                # A thread cannot be cancelled. Keep its permit until resources
                # are closed, and never start a provider call after cancellation.
                await asyncio.gather(rendering, return_exceptions=True)
                raise
    measurements = [layout.critique()] if layout else []
    if not config.merged_advisory:
        inputs = _panel_inputs(
            content,
            profile_facts,
            jd_text,
            config,
            coverage=coverage,
            depth_plan=depth_plan,
        )
        outputs = await asyncio.gather(
            *(
                areview_one(
                    text,
                    reviewer_agents[name],
                    sem=sem,
                    expected_reviewer=name,
                    layout=layout if name == "concision" else None,
                )
                for name, text in inputs
            ),
            return_exceptions=True,
        )
        return measurements + _settled_critiques(outputs)

    evidence = resolve_evidence(content, profile_facts)
    evidence_specs = [spec for spec in config.reviewers if spec.requires_evidence]
    advisory_names = _advisory_names(config)
    calls: list[Coroutine[Any, Any, Any]] = [
        areview_one(
            compose_evidence_review_input(content, jd_text, evidence),
            reviewer_agents[spec.name],
            sem=sem,
            expected_reviewer=spec.name,
            layout=layout if spec.name == "concision" else None,
        )
        for spec in evidence_specs
    ]
    if advisory_names:
        visual = layout if "concision" in advisory_names else None
        calls.append(
            acall(
                reviewer_agents[MERGED_ADVISORY],
                compose_lean_review_input(
                    content,
                    jd_text,
                    resume_stats(content),
                    coverage=coverage,
                    depth_plan=depth_plan,
                )
                + (visual.prompt() if visual else ""),
                sem=sem,
                images=visual.images if visual else (),
            )
        )
    outputs = await asyncio.gather(*calls, return_exceptions=True)
    critiques: list[ReviewCritique] = measurements.copy()
    first_error: BaseException | None = None
    for index, output in enumerate(outputs):
        if isinstance(output, BaseException):
            first_error = first_error or output
        elif advisory_names and index == len(evidence_specs):
            try:
                critiques.extend(_merged_review(output, advisory_names))
            except (TypeError, ValueError) as exc:
                first_error = first_error or exc
        else:
            critiques.append(output)
    if first_error is not None:
        raise first_error
    return critiques


def _settled_critiques(
    outputs: list[ReviewCritique | BaseException],
) -> list[ReviewCritique]:
    critiques: list[ReviewCritique] = []
    first_error: BaseException | None = None
    for output in outputs:
        if isinstance(output, BaseException):
            first_error = first_error or output
        else:
            critiques.append(output)
    if first_error is not None:
        raise first_error
    return critiques
