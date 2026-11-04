import json

import pytest
from pydantic import ValidationError
from resume_tailor_harness.models.base import Source

from resume_tailor_harness.models.importance import (
    FactImportanceScore,
    FactImportanceSignals,
)
from resume_tailor_harness.models.profile import (
    AdditionalEntry,
    AdditionalSection,
    Award,
    Bullet,
    Certification,
    Contact,
    Education,
    Experience,
    GitHubProfile,
    Language,
    ProfileFacts,
    Project,
    Publication,
    Skill,
    Volunteer,
)
from resume_tailor_harness.profile.importance import importance_value, score_profile
from resume_tailor_harness.profile.store import load_facts, save_facts
from resume_tailor_harness.profile.ids import assign_fact_ids
from resume_tailor_harness.profile.matrix import facts_sha256
from resume_tailor_harness.profile.conversation import (
    AppliedChange,
    ProfileChange,
    apply_change,
    change_schema,
)
from resume_tailor_harness.tailor.provenance import (
    check_provenance,
    index_facts,
    renderable_skill_pointer,
)
from resume_tailor_harness.models.resume import ResumeContent


def test_score_has_explainable_weighted_components_and_does_not_mutate_evidence():
    bullet = Bullet(
        id="result",
        text="Reduced latency from 500ms to 200ms",
        source_ref="resume",
        importance=FactImportanceSignals(
            significance=4,
            essentiality=3,
            impact=3,
            ownership=2,
        ),
        # A model or older file cannot set the authoritative total.
        importance_score=FactImportanceScore(score=100),
    )
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        experience=[
            Experience(id="work", company="Acme", title="Engineer", bullets=[bullet])
        ],
    )
    before = facts.model_dump_json()

    scored = score_profile(facts)
    result = scored.experience[0].bullets[0]
    score = result.importance_score
    assert score is not None
    assert score.score == 83.75
    assert score.components == {
        "significance": 25,
        "essentiality": 15,
        "context": 20,
        "impact": 11.25,
        "ownership": 5,
        "evidence": 7.5,
    }
    assert score.method == "assessed"
    assert score.context == "professional"
    assert result.id == bullet.id and result.text == bullet.text
    assert facts.model_dump_json() == before
    assert score_profile(scored) == scored


def test_context_is_a_bounded_advantage_and_strong_academic_work_can_win():
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        experience=[
            Experience(
                company="Acme",
                title="Assistant",
                importance=FactImportanceSignals(
                    significance=1,
                    essentiality=1,
                ),
            ),
        ],
        projects=[
            Project(
                name="Capstone",
                importance=FactImportanceSignals(
                    context="academic_project",
                    significance=4,
                    essentiality=4,
                    impact=4,
                    ownership=4,
                ),
            ),
            Project(
                name="Side project",
                importance=FactImportanceSignals(
                    context="personal_project",
                    significance=4,
                    essentiality=4,
                    impact=4,
                    ownership=4,
                ),
            ),
        ],
    )
    scored = score_profile(facts)

    assert importance_value(scored.projects[0]) > importance_value(scored.experience[0])
    assert (
        importance_value(scored.projects[1]) - importance_value(scored.projects[0]) == 2
    )


def test_unstated_repository_context_is_unknown_and_popularity_is_not_importance():
    original = Project(
        name="Service",
        source=Source.github,
        stars=1,
        forks=0,
        highlights=[Bullet(text="Implemented a queue", aspect="technical")],
    )
    duplicate = original.model_copy(
        deep=True,
        update={
            "stars": 100_000,
            "forks": 20_000,
            "highlights": original.highlights * 20,
        },
    )
    scored = score_profile(
        ProfileFacts(contact=Contact(name="Ada"), projects=[original, duplicate])
    )

    assert scored.projects[0].importance_score is not None
    assert scored.projects[0].importance_score.context == "unknown"
    assert importance_value(scored.projects[0]) == importance_value(scored.projects[1])


def test_restored_dossier_evidence_informs_owner_even_with_a_metadata_assessment():
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        projects=[
            Project(
                name="Compiler",
                importance=FactImportanceSignals(
                    context="academic_project",
                    significance=1,
                    essentiality=1,
                ),
                highlights=[
                    Bullet(
                        text="Implemented the parser",
                        importance=FactImportanceSignals(
                            significance=4,
                            essentiality=4,
                            impact=3,
                            ownership=2,
                        ),
                    )
                ],
            )
        ],
    )
    scored = score_profile(facts)
    score = scored.projects[0].importance_score
    assert score is not None
    assert score.components["significance"] == 25
    assert score.components["impact"] == 11.25
    assert score.context == "academic_project"
    assert scored.projects[0].importance == facts.projects[0].importance


def test_every_addressable_fact_gets_a_score_and_skill_context_follows_literal_evidence():
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        experience=[
            Experience(
                id="job",
                company="Acme",
                title="Engineer",
                bullets=[
                    Bullet(id="build", text="Built Python APIs", aspect="technical"),
                ],
            )
        ],
        education=[Education(institution="University")],
        projects=[Project(name="Project", highlights=[Bullet(text="Built a service")])],
        certifications=[Certification(name="Certificate")],
        publications=[Publication(title="Paper")],
        awards=[Award(name="Award")],
        languages=[Language(language="English")],
        volunteer=[Volunteer(organization="Charity")],
        github_profile=GitHubProfile(username="ada"),
        additional_sections=[
            AdditionalSection(
                title="Teaching",
                entries=[
                    AdditionalEntry(title="Seminar"),
                ],
            )
        ],
        skills={
            "Languages": [
                Skill(name="Python", evidence_fact_ids=["build"]),
                Skill(
                    name="Analysis",
                    inferred=True,
                    category="soft",
                    evidence_fact_ids=["build"],
                    importance=FactImportanceSignals(significance=4, essentiality=4),
                ),
                Skill(
                    name="Missing",
                    inferred=True,
                    category="hard",
                    evidence_fact_ids=["ghost"],
                ),
            ]
        },
    )
    scored = score_profile(facts)
    records = [
        *scored.experience,
        *scored.experience[0].bullets,
        *scored.projects,
        *scored.projects[0].highlights,
        *scored.education,
        *scored.certifications,
        *scored.publications,
        *scored.awards,
        *scored.languages,
        *scored.volunteer,
        *scored.additional_sections[0].entries,
        *scored.skills["Languages"],
        scored.github_profile,
    ]
    assert all(
        record is not None and record.importance_score is not None for record in records
    )
    skill_score = scored.skills["Languages"][0].importance_score
    assert skill_score is not None
    assert skill_score.context == "professional"
    assert skill_score.components["evidence"] == 10
    missing_score = scored.skills["Languages"][2].importance_score
    assert missing_score is not None and missing_score.components["evidence"] == 0
    # High importance cannot turn an inferred soft skill or broken pointer into a claim.
    assert [
        skill.name
        for skill in scored.skills["Languages"]
        if renderable_skill_pointer(skill, index_facts(scored))
    ] == ["Python"]


def test_legacy_load_backfills_without_writing_and_save_refreshes_scores(tmp_path):
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        projects=[
            Project(name="Course project", highlights=[Bullet(text="Built a parser")]),
        ],
    )
    path = tmp_path / "facts.json"
    path.write_text(facts.model_dump_json(), encoding="utf-8")
    before = path.read_bytes()
    loaded = load_facts(path)
    assert loaded.projects[0].importance_score is not None
    assert loaded.projects[0].importance_score.method == "fallback"
    assert path.read_bytes() == before
    changed = loaded.model_copy(deep=True)
    changed.projects[0].importance = FactImportanceSignals(
        context="academic_project",
        significance=4,
        essentiality=4,
    )
    save_facts(changed, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["projects"][0]["importance_score"]["context"] == "academic_project"
    assert load_facts(path) == score_profile(changed)
    assert loaded.projects[0].importance is None


def test_matrix_binding_ignores_ranking_metadata_but_detects_changed_evidence():
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        experience=[
            Experience(
                id="work",
                company="Acme",
                title="Engineer",
                bullets=[
                    Bullet(id="build", text="Built Python APIs"),
                ],
            )
        ],
        skills={"Languages": [Skill(id="python", name="Python")]},
    )
    original_hash = facts_sha256(facts)
    # Captured with the pre-importance model and fingerprint implementation.
    assert (
        original_hash
        == "1b7f4b7beb3ddc34cdb59b53610d2e73fb349477f161413bce106ab67268d6b4"
    )
    scored = score_profile(facts)
    scored.experience[0].bullets[0].importance = FactImportanceSignals(significance=4)
    assert facts_sha256(score_profile(scored)) == original_hash
    scored.experience[0].bullets[0].text = "Built Java APIs"
    assert facts_sha256(scored) != original_hash


@pytest.mark.parametrize("category", ["importance", "importance_score"])
def test_matrix_binding_preserves_skill_categories_named_like_ranking_fields(category):
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        skills={category: [Skill(id="python", name="Python")]},
    )
    original_hash = facts_sha256(facts)
    assert facts_sha256(score_profile(facts)) == original_hash
    changed = facts.model_copy(deep=True)
    changed.skills[category][0].name = "Java"
    assert facts_sha256(changed) != original_hash


def test_assigning_source_ids_refreshes_traceability_and_retains_assessments():
    signals = FactImportanceSignals(context="academic_project", significance=4)
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        projects=[
            Project(
                name="Compiler",
                importance=signals,
                highlights=[
                    Bullet(text="Implemented a parser", importance=signals),
                ],
            ),
        ],
    )
    scored = assign_fact_ids(facts, "source-doc")
    highlight = scored.projects[0].highlights[0]
    assert highlight.importance == signals
    assert highlight.source_ref == "source-doc"
    assert highlight.importance_score is not None
    assert highlight.importance_score.components["evidence"] == 7.5
    assert highlight.importance_score.context == "academic_project"


@pytest.mark.parametrize(
    "payload",
    [
        {"significance": 5},
        {"essentiality": -1},
        {"impact": 5},
        {"ownership": -1},
        {"context": "famous_company"},
    ],
)
def test_invalid_assessments_are_rejected_at_the_model_boundary(payload):
    with pytest.raises(ValidationError):
        FactImportanceSignals.model_validate(payload)


def test_verbatim_gates_compare_source_values_without_requiring_ranking_metadata():
    facts = score_profile(
        ProfileFacts(
            contact=Contact(name="Ada"),
            education=[Education(id="degree", institution="University")],
            languages=[Language(id="language", language="English")],
            additional_sections=[
                AdditionalSection(
                    title="Teaching",
                    entries=[
                        AdditionalEntry(
                            id="seminar", title="Seminar", description="Taught parsing"
                        ),
                    ],
                )
            ],
        )
    )
    cleared = {"importance": None, "importance_score": None}
    content = ResumeContent(
        contact=facts.contact,
        education=[facts.education[0].model_copy(update=cleared)],
        languages=[facts.languages[0].model_copy(update=cleared)],
        additional_sections=[
            AdditionalSection(
                title="Teaching",
                entries=[
                    facts.additional_sections[0].entries[0].model_copy(update=cleared),
                ],
            )
        ],
    )
    assert check_provenance(content, facts).ok
    content.education[0].institution = "Other University"
    content.languages[0].proficiency = "Fluent"
    content.additional_sections[0].entries[0].description = "Taught compilers"
    report = check_provenance(content, facts)
    assert not report.ok
    assert len(report.invalid) == 3


def test_conversation_cannot_set_scores_and_semantic_edits_retire_stale_assessments():
    facts = score_profile(
        ProfileFacts(
            contact=Contact(name="Ada"),
            experience=[
                Experience(
                    id="work",
                    company="Acme",
                    title="Engineer",
                    bullets=[
                        Bullet(
                            id="b",
                            text="Owned the service",
                            importance=FactImportanceSignals(
                                significance=4,
                                essentiality=4,
                                ownership=4,
                            ),
                        ),
                    ],
                ),
            ],
        )
    )
    schema = change_schema("fact", "bullets")
    assert "importance" not in schema["fields"]
    assert "importance_score" not in schema["fields"]
    for field, value in (
        ("importance_score", {"score": 100}),
        ("importance", {"significance": 4}),
    ):
        with pytest.raises(ValueError, match="Unsupported fields"):
            apply_change(
                facts,
                AppliedChange(
                    change=ProfileChange(
                        entity="fact",
                        operation="update",
                        section="bullets",
                        target_id="b",
                        parent_id="work",
                        values={field: value},
                        quotes=["Update this"],
                    )
                ),
            )
    changed, _ = apply_change(
        facts.model_copy(deep=True),
        AppliedChange(
            source_ref="approved-note",
            change=ProfileChange(
                entity="fact",
                operation="update",
                section="bullets",
                target_id="b",
                parent_id="work",
                values={"text": "Contributed documentation"},
                quotes=["Contributed documentation"],
            ),
        ),
    )
    assert changed is not None
    updated = score_profile(changed).experience[0].bullets[0]
    assert updated.importance is None
    assert updated.importance_score is not None
    assert updated.importance_score.method == "fallback"
    assert importance_value(updated) < importance_value(facts.experience[0].bullets[0])
