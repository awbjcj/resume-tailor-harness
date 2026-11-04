import pytest

from resume_tailor_harness.models.evidence_portfolio import (
    EvidencePortfolio,
    PortfolioSelection,
)
from resume_tailor_harness.models.importance import FactImportanceSignals
from resume_tailor_harness.models.job import JobCriteria
from resume_tailor_harness.models.profile import (
    Bullet,
    Contact,
    Experience,
    ProfileFacts,
    Project,
)
from resume_tailor_harness.profile.matrix import (
    MatrixRow,
    SkillMatch,
    SkillMatchContext,
)
from resume_tailor_harness.tailor.evidence_portfolio import (
    build_evidence_catalog,
    build_fallback_portfolio,
    normalize_evidence_portfolio,
    portfolio_profile,
)
from resume_tailor_harness.tailor.review_config import LengthBudget
from resume_tailor_harness.tailor.tailoring import compose_tailor_input
from resume_tailor_harness.tailor.length import format_depth_plan
from resume_tailor_harness.tailor.depth import depth_report
from resume_tailor_harness.models.resume import ResumeContent


def _signals(level: int) -> FactImportanceSignals:
    return FactImportanceSignals(
        significance=level, essentiality=level, impact=level, ownership=level
    )


def _projects() -> ProfileFacts:
    return ProfileFacts(
        contact=Contact(name="Ada"),
        projects=[
            Project(
                id="weak",
                name="Course exercise",
                importance=_signals(1),
                highlights=[
                    Bullet(
                        id=f"weak-{index}",
                        text=f"Exercise step {index}",
                        importance=_signals(1),
                    )
                    for index in range(3)
                ],
            ),
            Project(
                id="strong",
                name="Core system",
                importance=_signals(4),
                highlights=[
                    Bullet(
                        id=f"strong-{index}",
                        text=f"System contribution {index}",
                        importance=_signals(4),
                    )
                    for index in range(3)
                ],
            ),
        ],
    )


def test_fallback_allocates_more_distinct_bullets_to_stronger_equally_relevant_owners():
    facts = _projects()
    catalog = build_evidence_catalog(facts, JobCriteria(), None)
    budget = LengthBudget(
        max_projects=2,
        max_evidence_owners=2,
        max_bullets_per_project=3,
        target_total_bullets=4,
    )
    portfolio = build_fallback_portfolio(catalog, facts, JobCriteria(), None, budget)

    assert [(item.owner_id, item.bullet_budget) for item in portfolio.selections] == [
        ("strong", 3),
        ("weak", 1),
    ]
    assert portfolio.selections[0].selected_fact_ids == [
        "strong-0",
        "strong-1",
        "strong-2",
    ]
    assert portfolio.selections[1].selected_fact_ids == ["weak-0"]
    sliced = portfolio_profile(facts, portfolio)
    assert [project.id for project in sliced.projects] == ["strong", "weak"]
    assert len(sliced.projects[1].highlights) == 1
    assert len(facts.projects[0].highlights) == 3


def test_required_job_coverage_outranks_intrinsic_importance():
    facts = _projects()
    context = SkillMatchContext(
        matches=[
            SkillMatch(
                requirement="Python",
                source="must",
                coverage="covered",
                row=MatrixRow(
                    key="python", display="Python", evidence_fact_ids=["weak-0"]
                ),
            )
        ]
    )
    criteria = JobCriteria(must_have_skills=["Python"])
    catalog = build_evidence_catalog(facts, criteria, context)
    portfolio = build_fallback_portfolio(
        catalog,
        facts,
        criteria,
        context,
        LengthBudget(
            max_projects=1,
            max_evidence_owners=1,
            max_bullets_per_project=1,
            target_total_bullets=1,
        ),
    )
    assert portfolio.selections[0].owner_id == "weak"
    assert portfolio.selections[0].selected_fact_ids == ["weak-0"]


@pytest.mark.parametrize("level", [2, 4])
def test_essential_unquantified_fact_beats_incidental_metric_and_retains_rank_in_prompt(
    level,
):
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        experience=[
            Experience(
                id="work",
                company="Acme",
                title="Engineer",
                bullets=[
                    Bullet(
                        id="minor", text="Updated 20 documents", importance=_signals(1)
                    ),
                    Bullet(
                        id="core",
                        text="Owned the service architecture",
                        importance=_signals(level),
                    ),
                ],
            )
        ],
    )
    catalog = build_evidence_catalog(facts, JobCriteria(), None)
    budget = LengthBudget(max_bullets_per_role=1, target_total_bullets=1)
    portfolio = build_fallback_portfolio(catalog, facts, JobCriteria(), None, budget)
    assert portfolio.selections[0].selected_fact_ids == ["core"]
    assert portfolio_profile(facts, portfolio).experience[0].bullets[0].id == "core"
    prompt = compose_tailor_input("Job", JobCriteria(), facts)
    assert '"importance_score"' in prompt and '"components"' in prompt


def test_normalization_ranks_supplied_facts_before_truncating_and_bounds_frequency():
    facts = _projects()
    facts.projects[0].highlights[1].importance = _signals(4)
    catalog = build_evidence_catalog(facts, JobCriteria(), None)
    draft = EvidencePortfolio(
        selections=[
            PortfolioSelection(
                owner_id="weak",
                owner_kind="project",
                selected_fact_ids=["weak-0", "ghost", "weak-1"],
                bullet_budget=100,
            )
        ]
    )
    normalized = normalize_evidence_portfolio(
        draft,
        catalog,
        facts,
        JobCriteria(),
        None,
        LengthBudget(max_bullets_per_project=1, target_total_bullets=1),
    )
    assert normalized.selections[0].selected_fact_ids == ["weak-1"]
    assert normalized.selections[0].bullet_budget == 1
    assert normalized.evidence_excerpts[0].fact_id == "weak-1"


def test_legacy_project_owner_selection_still_keeps_full_project_evidence():
    facts = _projects()
    portfolio = EvidencePortfolio(
        selections=[
            PortfolioSelection(
                owner_id="weak",
                owner_kind="project",
                selected_fact_ids=["weak"],
                bullet_budget=2,
            )
        ]
    )
    assert len(portfolio_profile(facts, portfolio).projects[0].highlights) == 3


def test_weighted_allocation_is_the_same_depth_contract_for_writer_and_review():
    facts = _projects()
    catalog = build_evidence_catalog(facts, JobCriteria(), None)
    budget = LengthBudget(
        max_projects=2,
        max_evidence_owners=2,
        max_bullets_per_project=3,
        target_total_bullets=4,
    )
    portfolio = build_fallback_portfolio(catalog, facts, JobCriteria(), None, budget)
    plan = format_depth_plan(facts, budget, portfolio)
    assert 'weak "Course exercise": 1 source -> render 1' in plan
    assert 'strong "Core system": 3 source -> render 3' in plan
    prompt = compose_tailor_input(
        "Job", JobCriteria(), facts, budget, evidence_portfolio=portfolio
    )
    assert plan in prompt
    report = depth_report(
        ResumeContent(contact=Contact(name="Ada")), facts, budget, portfolio
    )
    assert [(item.id, item.floor) for item in report.owners] == [
        ("strong", 3),
        ("weak", 1),
    ]


def test_depth_contract_excludes_omitted_owners_and_honors_legacy_project_budget():
    facts = _projects()
    portfolio = EvidencePortfolio(
        selections=[
            PortfolioSelection(
                owner_id="weak",
                owner_kind="project",
                selected_fact_ids=["weak"],
                bullet_budget=1,
            )
        ]
    )
    plan = format_depth_plan(facts, LengthBudget(), portfolio)
    assert 'weak "Course exercise": 1 source -> render 1' in plan
    assert "Core system" not in plan
