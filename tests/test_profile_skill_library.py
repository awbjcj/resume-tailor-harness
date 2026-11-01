from types import SimpleNamespace

import pytest

from resume_tailor_harness.models.profile import (
    Bullet,
    Contact,
    Experience,
    ProfileFacts,
    Skill,
)
from resume_tailor_harness.profile.group_corrections import (
    GroupCorrection,
    GroupCorrections,
    corrections_path,
    load_group_corrections,
    save_group_corrections,
)
from resume_tailor_harness.profile.manual_skills import (
    apply_manual_skills,
    load_manual_skills,
)
from resume_tailor_harness.profile.matrix import load_matrix
from resume_tailor_harness.profile.store import load_facts, save_facts
from resume_tailor_harness.services import profile_groups, profile_skills
from resume_tailor_harness.services import profile_skill_build as build
from resume_tailor_harness.taxonomy.groups import (
    SkillGroupAssignment,
    SkillGroupAssignments,
)


@pytest.fixture()
def library(tmp_path):
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        experience=[
            Experience(
                id="role",
                company="Acme",
                title="Engineer",
                bullets=[Bullet(id="work", text="Built APIs in Python")],
            )
        ],
        skills={
            "hard": [
                Skill(
                    id="python",
                    name="Python",
                    aliases=["py"],
                    category="hard",
                    source_ref="resume:skills",
                ),
                Skill(
                    id="py3",
                    name="Python 3",
                    category="hard",
                    evidence_fact_ids=["work"],
                    source_ref="project:skills",
                ),
                Skill(id="travel", name="Willingness to travel", category="hard"),
            ]
        },
    )
    save_facts(facts, tmp_path / "facts.json")
    return tmp_path, facts


def _skills(directory):
    return [
        s
        for bucket in load_facts(directory / "facts.json").skills.values()
        for s in bucket
    ]


def _matrix(directory):
    matrix = load_matrix(directory / "matrix.json")
    assert matrix is not None
    return matrix


def test_edit_preserves_identity_evidence_and_replays_after_rebuild(library):
    directory, original = library
    profile_skills.update_skill(
        directory,
        "python",
        "Python programming",
        ["CPython"],
        "domain",
        group="languages",
    )
    updated = next(s for s in _skills(directory) if s.id == "python")
    assert updated.name == "Python programming"
    assert updated.source_ref == "resume:skills"
    assert updated.aliases == ["CPython", "Python"]
    replay, warnings = apply_manual_skills(
        original, load_manual_skills(directory / "manual_skills.json")
    )
    assert not warnings
    assert (
        next(s for s in replay.skills["domain"] if s.id == "python").name
        == updated.name
    )
    assert _matrix(directory).rows[0].group == "languages"


def test_merge_keeps_aliases_sources_and_evidence_and_survives_replay(library):
    directory, original = library
    profile_skills.merge_skills(directory, ["python", "python 3"], "python")
    merged = next(s for s in _skills(directory) if s.name == "Python")
    assert merged.id == "python"
    assert set(merged.aliases) == {"py", "Python 3"}
    assert merged.evidence_fact_ids == ["work"]
    assert set(merged.source_refs) == {"resume:skills", "project:skills"}
    replay, _ = apply_manual_skills(
        original, load_manual_skills(directory / "manual_skills.json")
    )
    assert len([s for bucket in replay.skills.values() for s in bucket]) == 2


def test_cleanup_preview_is_read_only_and_restore_is_immediate_and_protected(library):
    directory, original = library
    before = (directory / "facts.json").read_bytes()
    preview = profile_skills.cleanup_skills(directory)
    assert len(preview.pruned) == 1
    assert (directory / "facts.json").read_bytes() == before
    assert not (directory / "manual_skills.json").exists()
    profile_skills.cleanup_skills(directory, apply=True)
    assert [s.name for s in _skills(directory)] == ["Python", "Python 3"]
    profile_skills.restore_skill(directory, "willingness to travel")
    assert any(s.id == "travel" for s in _skills(directory))
    assert profile_skills.cleanup_skills(directory).pruned == []
    replay, _ = apply_manual_skills(
        original, load_manual_skills(directory / "manual_skills.json")
    )
    assert sum(map(len, replay.skills.values())) == 3


def test_cleanup_merges_explicit_aliases_without_fuzzy_pruning(library):
    directory, facts = library
    facts.skills["hard"][1].aliases = ["Python"]
    facts.skills["hard"].extend(
        [
            Skill(name="C"),
            Skill(name="C++"),
            Skill(name="C#"),
            Skill(name="数据分析"),
            Skill(name="沟通"),
        ]
    )
    save_facts(facts, directory / "facts.json")
    report = profile_skills.cleanup_skills(directory, apply=True)
    assert len(report.merges) == 1
    names = {s.name for s in _skills(directory)}
    assert {"C", "C++", "C#", "数据分析", "沟通"} <= names
    assert sum(name in names for name in ["Python", "Python 3"]) == 1
    again = profile_skills.cleanup_skills(directory)
    assert not again.merges and not again.pruned


def test_all_artifacts_roll_back_when_matrix_save_fails(library, monkeypatch):
    directory, _ = library
    before = (directory / "facts.json").read_bytes()
    monkeypatch.setattr(
        profile_skills,
        "rebuild_saved_matrix",
        lambda *_: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError):
        profile_skills.update_skill(
            directory, "python", "Renamed", [], "hard", group="languages"
        )
    assert (directory / "facts.json").read_bytes() == before
    assert not (directory / "manual_skills.json").exists()
    assert not corrections_path(directory).exists()


def test_custom_category_and_group_crud_and_deletion_keeps_skills(library):
    directory, _ = library
    organization = profile_groups.edit_organization(
        directory, "category", label="My specialty"
    )
    category = next(
        k
        for k, v in organization.category_catalog().items()
        if v.label == "My specialty"
    )
    organization = profile_groups.edit_organization(
        directory, "group", label="Runtime tools", category=category
    )
    group = next(
        k for k, v in organization.group_catalog().items() if v.label == "Runtime tools"
    )
    profile_groups.set_group(directory, "python", group)
    assert _matrix(directory).rows[0].group == group
    profile_groups.edit_organization(
        directory, "group", key=group, label="Runtime", category="technical"
    )
    assert (
        load_group_corrections(corrections_path(directory)).group_catalog()[group].label
        == "Runtime"
    )
    profile_groups.edit_organization(directory, "category", key=category, delete=True)
    profile_groups.edit_organization(directory, "group", key=group, delete=True)
    assert len(_skills(directory)) == 3
    assert (
        group not in load_group_corrections(corrections_path(directory)).group_catalog()
    )


def test_corrupt_organization_blocks_mutations_without_overwriting(library):
    directory, _ = library
    path = corrections_path(directory)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        profile_groups.edit_organization(directory, "category", label="New")
    assert path.read_text() == "{broken"


def test_reclassify_uses_custom_catalog_and_keeps_manual_assignment(
    library, monkeypatch
):
    directory, _ = library
    organization = GroupCorrections(
        corrections={"python": GroupCorrection(group="languages")}
    )
    save_group_corrections(organization, corrections_path(directory))
    prompts = []

    class Classifier:
        def run(self, prompt):
            import json

            payload = json.loads(prompt)
            prompts.append(payload)
            return SimpleNamespace(
                content=SkillGroupAssignments(
                    assignments=[
                        SkillGroupAssignment(token=t, group="backend-apis")
                        for t in payload["skills"]
                    ]
                )
            )

    monkeypatch.setattr(build, "build_profile_group_agent", lambda: Classifier())
    report = build.rebuild_profile_skills(directory, reclassify_only=True)
    assert report["classified"] == 1
    assert prompts[0]["skills"] == ["python 3"]
    matrix = _matrix(directory)
    assert {r.key: r.group for r in matrix.rows} == {
        "python": "languages",
        "python 3": "backend-apis",
    }


def test_rebuild_rejects_stale_output_and_preserves_concurrent_edit(
    library, monkeypatch
):
    directory, _ = library

    class Classifier:
        def run(self, _prompt):
            profile_skills.add_skill(directory, "Rust", "hard")
            return SimpleNamespace(
                content=SkillGroupAssignments(
                    assignments=[
                        SkillGroupAssignment(token="python", group="languages")
                    ]
                )
            )

    monkeypatch.setattr(build, "build_profile_group_agent", lambda: Classifier())
    with pytest.raises(ValueError, match="changed during"):
        build.rebuild_profile_skills(directory, reclassify_only=True)
    assert any(s.name == "Rust" for s in _skills(directory))
    assert any(s.name == "Willingness to travel" for s in _skills(directory))


def test_skill_rebuild_infers_from_profile_evidence_and_keeps_manual_changes(
    library, monkeypatch
):
    from resume_tailor_harness.profile.inference import InferredSkill

    directory, _ = library
    profile_skills.update_skill(
        directory, "python", "Python programming", ["py"], "hard", group="languages"
    )
    monkeypatch.setattr(build, "build_inference_agent", lambda: object())

    def infer(facts, _agent):
        assert all(not s.inferred for bucket in facts.skills.values() for s in bucket)
        return [
            InferredSkill(
                name="API development", category="hard", evidence_fact_ids=["work"]
            )
        ]

    monkeypatch.setattr(build, "infer_skills", infer)

    class Classifier:
        def run(self, prompt):
            import json

            return SimpleNamespace(
                content=SkillGroupAssignments(
                    assignments=[
                        SkillGroupAssignment(token=t, group="backend-apis")
                        for t in json.loads(prompt)["skills"]
                    ]
                )
            )

    monkeypatch.setattr(build, "build_profile_group_agent", lambda: Classifier())
    report = build.rebuild_profile_skills(directory)
    build.rebuild_profile_skills(directory)
    assert report["inferred"] == ["API development"]
    assert next(
        s for s in _skills(directory) if s.name == "API development"
    ).evidence_fact_ids == ["work"]
    assert any(s.name == "Python programming" for s in _skills(directory))
    assert (
        next(
            r for r in _matrix(directory).rows if r.display == "Python programming"
        ).group_source
        == "correction"
    )


@pytest.mark.parametrize("enabled", [True, False])
def test_full_profile_build_applies_cleanup_policy_and_persists_restore_data(
    library, monkeypatch, enabled
):
    from resume_tailor_harness.profile.build import BuildReport
    from resume_tailor_harness.services.profile_build import run_corpus_build

    directory, original = library
    monkeypatch.setattr(
        "resume_tailor_harness.profile.build.build_corpus_profile",
        lambda *_args, **_kwargs: (original.model_copy(deep=True), BuildReport()),
    )
    monkeypatch.setattr(
        "resume_tailor_harness.services.match_gap.refresh_clusters",
        lambda *_args, **_kwargs: {},
    )
    profile_skills.set_cleanup_policy(directory, enabled)
    report = run_corpus_build(
        profile_dir=directory, facts_out=directory / "facts.json", github_username=None
    )
    assert any(s.name == "Willingness to travel" for s in _skills(directory)) is (
        not enabled
    )
    assert bool(report["skillCleanup"]) is enabled
    if enabled:
        profile_skills.restore_skill(directory, "willingness to travel")
        assert any(s.id == "travel" for s in _skills(directory))


def test_cleanup_honors_explicitly_separated_canonicals(library):
    directory, facts = library
    facts.skills["hard"][1].aliases = ["Python"]
    save_facts(facts, directory / "facts.json")
    (directory / "overrides.yaml").write_text(
        "forbid_alias:\n  - [python, python 3]\n", encoding="utf-8"
    )
    report = profile_skills.cleanup_skills(directory, apply=True)
    assert report.merges == []
    assert {"Python", "Python 3"} <= {s.name for s in _skills(directory)}


def test_suppression_replays_against_a_new_primary_name_with_the_old_alias(library):
    directory, facts = library
    profile_skills.delete_skill(directory, "python")
    facts.skills["hard"][0].name = "Python programming"
    facts.skills["hard"][0].aliases = ["Python", "py"]
    updated, _ = apply_manual_skills(
        facts, load_manual_skills(directory / "manual_skills.json")
    )
    assert not any(
        s.id == "python" for bucket in updated.skills.values() for s in bucket
    )


def test_manual_merge_remaps_inferred_skill_evidence(library):
    directory, facts = library
    facts.skills["hard"].append(
        Skill(
            name="Backend development",
            category="hard",
            inferred=True,
            evidence_fact_ids=["py3"],
        )
    )
    save_facts(facts, directory / "facts.json")
    profile_skills.merge_skills(directory, ["python", "python 3"], "python")
    inferred = next(s for s in _skills(directory) if s.inferred)
    assert inferred.evidence_fact_ids == ["python"]


def test_rebuild_rejects_concurrent_override_changes(library, monkeypatch):
    directory, _ = library
    before = (directory / "facts.json").read_bytes()

    class Classifier:
        def run(self, _prompt):
            (directory / "overrides.yaml").write_text(
                "ban: [Python]\n", encoding="utf-8"
            )
            return SimpleNamespace(
                content=SkillGroupAssignments(
                    assignments=[
                        SkillGroupAssignment(token="python", group="languages"),
                    ]
                )
            )

    monkeypatch.setattr(build, "build_profile_group_agent", lambda: Classifier())
    with pytest.raises(ValueError, match="changed during"):
        build.rebuild_profile_skills(directory, reclassify_only=True)
    assert (directory / "facts.json").read_bytes() == before
