"""Keep the authoring budget aligned with the selected rendering length."""

from resume_tailor_harness.services.rendering import DEFAULT_RENDER, _load_config
from resume_tailor_harness.render.render_config import RenderConfig
from resume_tailor_harness.tailor.review_config import ReviewConfig


def for_rendering(
    config: ReviewConfig, render: RenderConfig | None = None
) -> ReviewConfig:
    render = render or _load_config(DEFAULT_RENDER)
    pages = 1 if render.fit_one_page else 2
    return config.model_copy(
        update={"length_budget": config.length_budget.for_pages(pages)}
    )
