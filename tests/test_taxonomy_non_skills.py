import pytest

from resume_tailor_harness.taxonomy.clusters import ClusterMap
from resume_tailor_harness.taxonomy.non_skills import cleanup_candidates, non_skill_reason
from resume_tailor_harness.taxonomy.snapshot import EffectiveTaxonomy
from resume_tailor_harness.taxonomy.state import RetiredSkill, TaxonomyState


@pytest.mark.parametrize("token", [
    "8+ years of machine learning experience", "2 years", "10+ years building distributed infrastructure",
    "3-5 years of Python", "At least 5 years of experience", "Ten years of experience",
    "Bachelor's degree in computer engineering", "computer science degree",
    "Master s degree in mechanical engineering", "PhD in machine learning", "Ph.D. in computer vision",
    "active secret clearance", "u.s. citizenship", "TS/SCI clearance", "work authorization",
    "international travel", "travel up to 25%", "willingness to travel",
])
def test_backup_requirement_examples_are_cleanup_candidates(token):
    assert non_skill_reason(token) is not None


@pytest.mark.parametrize("token", [
    "Python", "computer science", "machine learning", "authorization", "authorization protocols",
    "authentication and authorization", "travel management", "multi year planning",
    "360 degree feedback", "degree of parallelism", "security engineering", "master data management",
    "scrum master", "bachelor algorithm", "five year strategic planning", "clearance analysis",
])
def test_real_skills_are_not_suggested_for_cleanup(token):
    assert non_skill_reason(token) is None


def test_cleanup_includes_assigned_and_demanded_but_not_retired_or_valid_alias_heads():
    taxonomy = EffectiveTaxonomy.from_parts(
        ClusterMap(
            aliases={"phd in machine learning": "machine learning", "travel": "international travel"},
            domain_of={"2 years": "languages", "machine learning": "ai", "international travel": "other"},
        ),
        state=TaxonomyState(retired_skills={"travel": RetiredSkill()}),
    )
    assert cleanup_candidates(taxonomy, ["computer science degree", "Python"]) == [
        {"key": "2 years", "reason": "Years-of-experience requirement"},
        {"key": "computer science degree", "reason": "Education or degree requirement"},
    ]
