from resume_tailor_harness.models.profile import Contact, ProfileFacts
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
)
from resume_tailor_harness.tailor.length import (
    format_budget,
    format_depth_plan,
    prepare_draft,
    resume_stats,
)
from resume_tailor_harness.tailor.review_config import LengthBudget, ReviewConfig


def test_length_budget_defaults_present_on_config():
    cfg = ReviewConfig()
    assert cfg.length_budget.page_target == 2
    assert cfg.length_budget.max_experiences == 5
    assert cfg.length_budget.max_bullets_per_role == 7
    assert cfg.length_budget.min_bullets_per_role == 5
    assert cfg.length_budget.min_bullets_per_project == 4
    assert cfg.length_budget.target_total_bullets == 40


def test_one_page_envelope_reconciles_legacy_depth_without_mutating_saved_budget():
    saved = LengthBudget()
    compact = saved.for_pages(1)
    assert saved.page_target == 2 and saved.target_total_bullets == 40
    assert compact.page_target == 1 and compact.target_total_bullets == 16
    assert (compact.min_bullets_per_role, compact.max_bullets_per_role) == (2, 4)
    assert (compact.min_bullets_per_project, compact.max_bullets_per_project) == (1, 3)
    assert compact.for_pages() == compact


def test_one_page_envelope_respects_lower_user_caps():
    compact = LengthBudget(
        max_experiences=1,
        max_projects=1,
        max_evidence_owners=2,
        max_bullets_per_role=1,
        max_bullets_per_project=1,
        target_total_bullets=2,
        target_skills=10,
    ).for_pages(1)
    assert compact.max_experiences == 1
    assert compact.min_bullets_per_role == compact.max_bullets_per_role == 1
    assert compact.target_total_bullets == 2 and compact.target_skills == 10


def test_one_page_draft_drops_summary_before_review_and_keeps_evidence():
    from resume_tailor_harness.render.sample_content import sample_resume_content

    original = sample_resume_content()
    original.summary = "A redundant profile summary."
    original.summary_provenance = ["sample-experience"]
    prepared = prepare_draft(original, LengthBudget(page_target=1))
    assert prepared.summary is None and prepared.summary_provenance == []
    assert prepared.experience == original.experience
    assert prepared.projects == original.projects
    assert prepared.skills == original.skills
    assert original.summary
    assert prepare_draft(original, LengthBudget(page_target=2)) is original


def test_one_page_prompt_prioritizes_work_over_summary_and_uses_realistic_floors():
    text = format_budget(LengthBudget(page_target=1))
    assert "Set summary to null" in text
    assert "professional experience and projects" in text
    assert "2–4 bullets" in text and "1–3" in text
    assert "16 bullets in total" in text


def test_budget_tells_the_writer_to_span_the_configured_aspects():
    text = format_budget(LengthBudget(min_aspects_per_owner=3))

    assert "at least 3 different aspects" in text


def test_depth_plan_omits_an_empty_profile():
    assert (
        format_depth_plan(ProfileFacts(contact=Contact(name="Ada")), LengthBudget())
        == ""
    )


def test_legacy_cap_only_budget_derives_an_achievable_floor():
    budget = LengthBudget(max_bullets_per_role=2, max_bullets_per_project=3)

    assert (budget.min_bullets_per_role, budget.min_bullets_per_project) == (2, 3)


def test_format_budget_mentions_page_target_and_numbers():
    text = format_budget(
        LengthBudget(
            page_target=2,
            max_experiences=3,
            max_bullets_per_role=6,
            min_bullets_per_role=4,
            target_total_bullets=15,
        )
    )
    assert "2 pages" in text
    assert "3" in text and "4" in text and "6" in text and "15" in text


def test_length_budget_declares_a_skills_target():
    # The budget bounded experiences, projects and bullets but said nothing at
    # all about skills, so "prefer the most relevant facts; drop the rest" was
    # the only signal the writer had for the skills section - and it cut it to
    # a fraction of the profile.
    cfg = ReviewConfig()
    assert cfg.length_budget.target_skills == 40
    assert cfg.length_budget.max_skills_per_category == 12


def test_format_budget_asks_for_skills_breadth_not_just_cuts():
    text = format_budget(LengthBudget(target_skills=36, max_skills_per_category=9))

    assert "36" in text and "9" in text
    # The instruction must state that skills are cheap in page space, otherwise
    # the one-page target is read as a reason to cut them like bullets.
    assert "adjacent" in text
    assert "skills" in text.lower()


def test_resume_stats_counts_experiences_projects_and_bullets():
    rc = ResumeContent(
        contact=Contact(name="Ada"),
        experience=[
            TailoredExperience(
                company="AE",
                title="Eng",
                provenance="e1",
                bullets=[
                    TailoredBullet(text="a", provenance="b1"),
                    TailoredBullet(text="b", provenance="b2"),
                ],
            )
        ],
        projects=[
            TailoredProject(
                name="Looms",
                provenance="p1",
                bullets=[TailoredBullet(text="c", provenance="p1b1")],
            )
        ],
    )
    stats = resume_stats(rc)
    assert "experiences=1" in stats
    assert "projects=1" in stats
    assert "total_bullets=3" in stats
