"""Optional resume sections retain their source and cannot bypass fact-lock."""

import pytest

from resume_tailor_harness.models.profile import (
    AdditionalEntry,
    AdditionalSection,
    Contact,
    ProfileFacts,
    Project,
    Bullet,
)
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredProject,
    TailoredBullet,
)
from resume_tailor_harness.profile.corpus import SourceDoc
from resume_tailor_harness.profile.ids import assign_fact_ids
from resume_tailor_harness.profile.merge import merge_fragments
from resume_tailor_harness.tailor.provenance import check_provenance, resolve_evidence
from resume_tailor_harness.tailor.numeric_evidence import numeric_evidence_critique


def _facts():
    return assign_fact_ids(
        ProfileFacts(
            contact=Contact(name="Alex"),
            projects=[
                Project(
                    name="Case Study",
                    url="https://example.com/work",
                    highlights=[Bullet(text="Built 3 tools.")],
                )
            ],
            interests=["Robotics"],
            additional_sections=[
                AdditionalSection(
                    title="Teaching",
                    entries=[
                        AdditionalEntry(
                            title="Systems Lab",
                            organization="University",
                            date="2024",
                            description="Taught 3 laboratory sessions.",
                        )
                    ],
                )
            ],
        ),
        "source",
    )


def test_additional_sections_have_stable_ids_and_review_evidence():
    facts = _facts()
    assert facts == _facts()
    content = ResumeContent(
        contact=facts.contact,
        additional_sections=facts.additional_sections,
        interests=facts.interests,
    )
    assert resolve_evidence(content, facts)["profile:interests"] == {
        "interests": ["Robotics"]
    }
    assert check_provenance(content, facts).ok
    entry = facts.additional_sections[0].entries[0]
    assert (
        resolve_evidence(content, facts)[entry.id]["description"] == entry.description
    )


@pytest.mark.parametrize(
    "field,value", [("title", "Nobel Prize"), ("description", "Taught 30 sessions.")]
)
def test_changed_additional_claims_fail_verbatim_gate(field, value):
    facts = _facts()
    content = ResumeContent(
        contact=facts.contact, additional_sections=facts.additional_sections
    ).model_copy(deep=True)
    setattr(content.additional_sections[0].entries[0], field, value)
    assert not check_provenance(content, facts).ok


def test_changed_section_heading_and_interests_cannot_create_facts():
    facts = _facts()
    content = ResumeContent(
        contact=facts.contact, additional_sections=facts.additional_sections
    ).model_copy(deep=True)
    content.additional_sections[0].title = "Honors"
    content.interests = ["Spaceflight"]
    report = check_provenance(content, facts)
    assert not report.ok and len(report.invalid) == 2


def test_portfolio_links_and_bullets_use_project_evidence():
    facts = _facts()
    project = facts.projects[0]
    content = ResumeContent(
        contact=facts.contact,
        portfolio=[
            TailoredProject(
                name=project.name,
                url=project.url,
                provenance=project.id,
                bullets=[
                    TailoredBullet(
                        text="Built 3 tools.", provenance=project.highlights[0].id
                    )
                ],
            )
        ],
    )
    assert check_provenance(content, facts).ok
    assert numeric_evidence_critique(content, facts).passed
    assert project.id in resolve_evidence(content, facts)
    content.portfolio[0].bullets[0].text = "Built 30 tools."
    assert not numeric_evidence_critique(content, facts).passed
    content.portfolio[0].url = "https://example.com/unsupported"
    assert not check_provenance(content, facts).ok


def test_portfolio_does_not_duplicate_projects_or_disappear_from_budget_stats():
    from resume_tailor_harness.tailor.length import resume_stats

    facts = _facts()
    project = facts.projects[0]
    entry = TailoredProject(name=project.name, provenance=project.id)
    content = ResumeContent(contact=facts.contact, portfolio=[entry])
    assert "projects=1" in resume_stats(content)
    content.projects = [entry]
    assert not check_provenance(content, facts).ok


def test_merge_preserves_additional_sections_from_supporting_sources():
    primary = ProfileFacts(contact=Contact(name="Alex"))
    secondary = _facts()
    merged, _ = merge_fragments(
        [
            (
                SourceDoc(
                    id="primary",
                    filename="resume.md",
                    primary=True,
                    sha256="primary-hash",
                    added_at="2026-10-31",
                ),
                primary,
            ),
            (
                SourceDoc(
                    id="source",
                    filename="teaching.md",
                    sha256="source-hash",
                    added_at="2026-10-31",
                ),
                secondary,
            ),
        ]
    )
    assert merged.additional_sections == secondary.additional_sections
    assert primary.additional_sections == []


def test_merge_keeps_non_latin_sections_and_distinct_dated_entries():
    primary = ProfileFacts(
        contact=Contact(name="Alex"),
        additional_sections=[
            AdditionalSection(
                title="教学", entries=[AdditionalEntry(title="课程", date="2024")]
            ),
        ],
    )
    secondary = ProfileFacts(
        contact=Contact(name="Alex"),
        additional_sections=[
            AdditionalSection(
                title="专利", entries=[AdditionalEntry(title="系统", date="2025")]
            ),
            AdditionalSection(
                title="教学", entries=[AdditionalEntry(title="课程", date="2025")]
            ),
        ],
    )
    merged, _ = merge_fragments(
        [
            (
                SourceDoc(
                    id="one",
                    filename="one.md",
                    sha256="one",
                    added_at="2026-10-31",
                    primary=True,
                ),
                primary,
            ),
            (
                SourceDoc(
                    id="two", filename="two.md", sha256="two", added_at="2026-10-31"
                ),
                secondary,
            ),
        ]
    )
    assert [section.title for section in merged.additional_sections] == ["教学", "专利"]
    assert [entry.date for entry in merged.additional_sections[0].entries] == [
        "2024",
        "2025",
    ]
