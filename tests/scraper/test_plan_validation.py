from resume_tailor_harness.discovery.scraper.browser_worker import snapshot_from_html
from resume_tailor_harness.discovery.scraper.contracts import BoardPlan, FieldRule
from resume_tailor_harness.discovery.scraper.validate import validate_plan


def test_unseen_detail_selector_cannot_approve_recipe():
    listing = snapshot_from_html(
        "https://example.com/jobs", '<article><a href="/jobs/1">Engineer</a></article>'
    )
    detail = snapshot_from_html(
        "https://example.com/jobs/1", "<h1>Engineer</h1><p>Actual description</p>"
    )
    plan = BoardPlan(
        card_selector="article", link_selector="a", detail_selector=".invented"
    )
    assert not validate_plan(plan, listing, [detail]).valid


def test_optional_field_absent_is_not_a_broken_description():
    page = snapshot_from_html(
        "https://example.com/jobs",
        '<article><h1>Engineer</h1><p class="jd">Build reliable systems with our engineering team.</p></article>',
    )
    plan = BoardPlan(
        card_selector="article",
        detail_mode="inline",
        detail_selector=".jd",
        field_rules=[FieldRule(field="salary_bands", selector=".salary")],
    )
    assert validate_plan(plan, page, [page]).valid


def test_invalid_css_is_a_reviewable_issue():
    page = snapshot_from_html("https://example.com/jobs", "<article>Job</article>")
    plan = BoardPlan(card_selector="[invalid", detail_mode="inline")
    assert not validate_plan(plan, page, [page]).valid
