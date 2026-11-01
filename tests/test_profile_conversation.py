"""Conversation edits must be reviewed, tenant-bound, durable and repeat-safe."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from resume_tailor_harness.models.profile import (
    Bullet,
    Contact,
    Experience,
    ProfileFacts,
    Skill,
)
from resume_tailor_harness.profile.coach import CoachTurn
from resume_tailor_harness.profile.coach_store import (
    CoachTopic,
    CoachTurnRecord,
    apply_turn_delta,
    create_session,
    load_session,
)
from resume_tailor_harness.profile.conversation import (
    ProfileChange,
    ProfileChangeSet,
    current_facts,
    load_edits,
    make_profile_tools,
    prepare_changes,
    replay_edits,
)
from resume_tailor_harness.profile.store import save_facts
from resume_tailor_harness.services.profile_conversation import (
    StaleProfileDraft,
    resolve_changes,
)
from resume_tailor_harness.services.profile_coach import run_message_turn


@pytest.fixture
def profile(tmp_path):
    save_facts(
        ProfileFacts(
            contact=Contact(name="Ada", email="ada@example.test"),
            experience=[
                Experience(
                    id="exp1",
                    company="Acme",
                    title="Engineer",
                    bullets=[Bullet(id="b1", text="Built a service")],
                )
            ],
            skills={
                "Programming": [Skill(id="sk1", name="Python", category="hard")],
                "Inferred": [
                    Skill(
                        id="sk2",
                        name="Design",
                        inferred=True,
                        category="hard",
                        evidence_fact_ids=["b1"],
                    )
                ],
            },
        ),
        tmp_path / "facts.json",
    )
    return tmp_path


def _facts(root) -> ProfileFacts:
    facts = current_facts(root)
    assert facts is not None
    return facts


def _change(**values):
    return ProfileChange(quotes=["Please make this change"], **values)


def _stage(root, changes, text="Please make this change"):
    if not (root / "coach" / "session-s1.json").exists():
        create_session(
            root,
            "s1",
            [CoachTopic(id="t1", gap="Profile")],
            CoachTurnRecord(
                role="coach",
                kind="question",
                text="What would you like to change?",
                topic_id="t1",
            ),
        )
    draft = prepare_changes(
        root,
        ProfileChangeSet(title="Requested changes", changes=changes),
        text,
        source_ref="coach:s1",
    )
    apply_turn_delta(
        root,
        "s1",
        user_text=text,
        coach_turn=CoachTurnRecord(
            role="coach", kind="profile_changes", text="Review these changes."
        ),
        new_topics=[],
        skipped_topic_ids=[],
        draft=None,
        change_draft=draft,
    )
    return draft


def _apply(root, draft, decision="apply"):
    resolve_changes(root, "s1", draft.id, decision=decision, revision=draft.revision)


def _bytes(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_tools_preview_and_draft_are_read_only(profile):
    before = _bytes(profile)
    inspect, schema, preview = make_profile_tools(
        profile, user_text="Please make this change"
    )
    assert inspect("skills")["records"][0]["id"] == "sk1"
    assert "source_ref" not in schema("skill")["fields"]
    proposal = ProfileChangeSet(
        title="Headline",
        changes=[
            _change(
                entity="profile",
                operation="update",
                values={"contact": {"headline": "Backend Engineer"}},
            )
        ],
    )
    result = preview(proposal)
    assert result["valid"] is True and result["saved"] is False
    assert _bytes(profile) == before
    draft = _stage(profile, proposal.changes)
    assert _facts(profile).contact.headline is None
    assert draft.previews[0].before == {"contact": {"headline": None}}
    assert load_session(profile, "s1")["change_drafts"][0]["status"] == "pending"


def test_approval_preserves_other_fields_and_is_idempotent_under_concurrency(profile):
    draft = _stage(
        profile,
        [
            _change(
                entity="profile",
                operation="update",
                values={"contact": {"headline": "Backend Engineer"}},
            )
        ],
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: _apply(profile, draft), range(2)))
    facts = _facts(profile)
    assert facts.contact.headline == "Backend Engineer"
    assert facts.contact.email == "ada@example.test"
    assert len(load_edits(profile).changes) == 1
    assert load_session(profile, "s1")["change_drafts"][0]["status"] == "applied"
    assert (profile / "matrix.json").exists()


def test_stale_draft_and_replaced_payload_cannot_apply(profile):
    draft = _stage(
        profile, [_change(entity="skill", operation="delete", target_id="sk1")]
    )
    with pytest.raises(StaleProfileDraft):
        resolve_changes(profile, "s1", draft.id, decision="apply", revision="0" * 64)
    changed = _facts(profile).model_copy(deep=True)
    changed.contact.name = "New name"
    save_facts(changed, profile / "facts.json")
    with pytest.raises(StaleProfileDraft):
        _apply(profile, draft)
    assert _facts(profile).skills["Programming"][0].name == "Python"
    _apply(
        profile, draft, decision="discard"
    )  # Discard remains available after a conflict.
    with pytest.raises(ValueError, match="resolved"):
        _apply(profile, draft)


@pytest.mark.parametrize(
    "values",
    [
        {"id": "forged"},
        {"source": "github"},
        {"inferred": False},
        {"evidence_fact_ids": ["b1"]},
        {"source_refs": ["forged-source"]},
        {"category": "Tooling"},
        {"name": 42},
    ],
)
def test_skill_changes_reject_unowned_fields_and_bad_types(profile, values):
    with pytest.raises(ValueError):
        _stage(
            profile,
            [
                _change(
                    entity="skill", operation="update", target_id="sk1", values=values
                )
            ],
        )
    assert _facts(profile).skills["Programming"][0].name == "Python"


def test_current_turn_evidence_and_exact_targets_are_required(profile):
    proposal = ProfileChangeSet(
        title="No old evidence",
        changes=[_change(entity="skill", operation="delete", target_id="sk1")],
    )
    with pytest.raises(ValueError, match="current user"):
        prepare_changes(profile, proposal, "What does this mean?", source_ref="test")
    with pytest.raises(ValueError, match="Unknown target"):
        _stage(
            profile,
            [
                _change(
                    entity="skill", operation="delete", target_id="another-tenant-id"
                )
            ],
        )
    with pytest.raises(ValueError, match="Unsupported fields"):
        _stage(
            profile,
            [
                _change(
                    entity="profile",
                    operation="update",
                    values={"contact": {"id": "forged"}},
                )
            ],
        )


def test_fact_edit_and_delete_survive_rebuild_and_remove_orphan_inference(profile):
    original = _facts(profile).model_copy(deep=True)
    draft = _stage(
        profile,
        [
            _change(
                entity="fact",
                operation="update",
                section="experience",
                target_id="exp1",
                values={"title": "Senior Engineer"},
            )
        ],
    )
    _apply(profile, draft)
    draft = _stage(
        profile,
        [
            _change(
                entity="fact",
                operation="delete",
                section="bullets",
                parent_id="exp1",
                target_id="b1",
            )
        ],
    )
    _apply(profile, draft)
    rebuilt, warnings = replay_edits(original, load_edits(profile))
    assert not warnings
    assert rebuilt.experience[0].title == "Senior Engineer"
    assert rebuilt.experience[0].id == "exp1"
    assert rebuilt.experience[0].bullets == []
    assert rebuilt.skills["Inferred"] == []


def test_corrected_fact_invalidates_inference_from_its_previous_content(profile):
    original = _facts(profile).model_copy(deep=True)
    _apply(
        profile,
        _stage(
            profile,
            [
                _change(
                    entity="fact",
                    operation="update",
                    section="bullets",
                    parent_id="exp1",
                    target_id="b1",
                    values={"text": "Coordinated a scheduling change"},
                )
            ],
        ),
    )
    assert _facts(profile).skills["Inferred"] == []
    rebuilt, warnings = replay_edits(original, load_edits(profile))
    assert not warnings and rebuilt.skills["Inferred"] == []


def test_skill_rename_move_and_delete_replay_with_new_source_ids(profile):
    original = _facts(profile).model_copy(deep=True)
    original.skills["Programming"][0].id = "rebuilt-id"
    draft = _stage(
        profile,
        [
            _change(
                entity="skill",
                operation="update",
                target_id="sk1",
                category="Languages",
                values={"name": "Python 3", "aliases": ["Python"]},
            )
        ],
    )
    _apply(profile, draft)
    facts = _facts(profile)
    assert facts.skills["Languages"][0].id == "sk1"
    rebuilt, warnings = replay_edits(original, load_edits(profile))
    assert not warnings and rebuilt.skills["Languages"][0].name == "Python 3"
    draft = _stage(
        profile, [_change(entity="skill", operation="delete", target_id="sk1")]
    )
    _apply(profile, draft)
    rebuilt, warnings = replay_edits(original, load_edits(profile))
    assert not warnings and not rebuilt.skills["Languages"]


def test_organizing_inferred_skill_does_not_promote_it_to_evidence(profile):
    draft = _stage(
        profile,
        [
            _change(
                entity="skill",
                operation="update",
                target_id="sk2",
                category="Design methods",
            )
        ],
    )
    assert draft.previews[0].before is not None
    assert draft.previews[0].after is not None
    assert draft.previews[0].before["display_bucket"] == "Inferred"
    assert draft.previews[0].after["display_bucket"] == "Design methods"
    _apply(profile, draft)
    skill = _facts(profile).skills["Design methods"][0]
    assert skill.inferred and skill.evidence_fact_ids == ["b1"]


def test_category_create_rename_delete_retains_member_skills(profile):
    for change in [
        _change(entity="skill_category", operation="create", values={"name": "Empty"}),
        _change(
            entity="skill_category",
            operation="update",
            target_id="Programming",
            values={"name": "Languages"},
        ),
        _change(entity="skill_category", operation="delete", target_id="Languages"),
    ]:
        _apply(profile, _stage(profile, [change]))
    facts = _facts(profile)
    assert "Empty" in facts.skills and "Languages" not in facts.skills
    assert facts.skills["Other"][0].name == "Python"


def test_category_membership_survives_source_bucket_and_id_changes(profile):
    original = _facts(profile).model_copy(deep=True)
    _apply(
        profile,
        _stage(
            profile,
            [
                _change(
                    entity="skill_category",
                    operation="update",
                    target_id="Programming",
                    values={"name": "My languages"},
                )
            ],
        ),
    )
    original.skills["Regenerated bucket"] = original.skills.pop("Programming")
    original.skills["Regenerated bucket"][0].id = "regenerated-id"
    rebuilt, warnings = replay_edits(original, load_edits(profile))
    assert not warnings
    assert rebuilt.skills["My languages"][0].name == "Python"


def test_create_remove_and_recreate_profile_without_sources(tmp_path):
    draft = _stage(
        tmp_path,
        [
            _change(
                entity="profile",
                operation="create",
                values={"contact": {"name": "Ada"}},
            )
        ],
    )
    _apply(tmp_path, draft)
    _apply(
        tmp_path,
        _stage(
            tmp_path,
            [
                _change(
                    entity="fact",
                    operation="create",
                    section="projects",
                    values={"name": "New project"},
                )
            ],
        ),
    )
    assert _facts(tmp_path).projects[0].source.value == "manual"
    original = _facts(tmp_path).model_copy(deep=True)
    _apply(tmp_path, _stage(tmp_path, [_change(entity="profile", operation="delete")]))
    assert not (tmp_path / "facts.json").exists()
    assert not (tmp_path / "matrix.json").exists()
    with pytest.raises(ValueError, match="removed"):
        replay_edits(original, load_edits(tmp_path))
    _apply(
        tmp_path,
        _stage(
            tmp_path,
            [
                _change(
                    entity="profile",
                    operation="create",
                    values={"contact": {"name": "Fresh profile"}},
                )
            ],
        ),
    )
    rebuilt, warnings = replay_edits(original, load_edits(tmp_path))
    assert (
        not warnings
        and rebuilt.contact.name == "Fresh profile"
        and rebuilt.projects == []
    )


def test_conversational_profile_rebuild_needs_no_primary_resume(tmp_path, monkeypatch):
    from resume_tailor_harness.services.profile_build import run_corpus_build

    _apply(
        tmp_path,
        _stage(
            tmp_path,
            [
                _change(
                    entity="profile",
                    operation="create",
                    values={"contact": {"name": "Ada"}},
                )
            ],
        ),
    )
    _apply(
        tmp_path,
        _stage(
            tmp_path,
            [
                _change(
                    entity="skill",
                    operation="create",
                    category="Languages",
                    values={"name": "Python", "category": "hard"},
                )
            ],
        ),
    )

    def no_model(*args, **kwargs):
        pytest.fail(
            "A conversational-only profile rebuild must not call an extraction model"
        )

    monkeypatch.setattr(
        "resume_tailor_harness.profile.build.build_corpus_profile", no_model
    )
    result = run_corpus_build(
        profile_dir=tmp_path, facts_out=tmp_path / "facts.json", github_username=None
    )
    assert result["matrixRows"] == 1
    assert _facts(tmp_path).contact.name == "Ada"
    assert _facts(tmp_path).skills["Languages"][0].name == "Python"


def test_failed_commit_rolls_back_facts_ledger_matrix_and_draft(profile, monkeypatch):
    draft = _stage(
        profile, [_change(entity="skill", operation="delete", target_id="sk1")]
    )
    before = _bytes(profile)

    def fail(*args):
        raise OSError("Disk full")

    monkeypatch.setattr(
        "resume_tailor_harness.services.profile_conversation.rebuild_saved_matrix", fail
    )
    with pytest.raises(OSError, match="Disk full"):
        _apply(profile, draft)
    after = _bytes(profile)
    after.pop(Path(".profile-mutations.lock"), None)
    assert after == before


def test_corrupt_ledger_fails_closed(profile):
    (profile / "conversation_edits.json").write_text("corrupt", encoding="utf-8")
    draft = _stage(
        profile,
        [
            _change(
                entity="profile", operation="update", values={"summary": "A summary"}
            )
        ],
    )
    with pytest.raises(ValueError):
        _apply(profile, draft)
    assert _facts(profile).summary is None


def test_later_direct_skill_edits_win_over_conversation_replay(profile):
    from resume_tailor_harness.services.profile_skills import (
        add_alias,
        add_skill,
        delete_skill,
        restore_skill,
    )
    from resume_tailor_harness.profile.manual_skills import (
        apply_manual_skills,
        load_manual_skills,
    )

    original = _facts(profile).model_copy(deep=True)
    _apply(
        profile,
        _stage(
            profile,
            [
                _change(
                    entity="skill",
                    operation="update",
                    target_id="sk1",
                    values={"aliases": ["Py"]},
                )
            ],
        ),
    )
    add_alias(profile, "sk1", "Python language")
    rebuilt, _ = apply_manual_skills(
        original, load_manual_skills(profile / "manual_skills.json")
    )
    rebuilt, _ = replay_edits(rebuilt, load_edits(profile))
    assert (
        "Python language"
        in next(
            s for b in rebuilt.skills.values() for s in b if s.name == "Python"
        ).aliases
    )
    delete_skill(profile, "Python")
    rebuilt, _ = apply_manual_skills(
        original, load_manual_skills(profile / "manual_skills.json")
    )
    rebuilt, _ = replay_edits(rebuilt, load_edits(profile))
    assert all(s.name != "Python" for bucket in rebuilt.skills.values() for s in bucket)
    restore_skill(profile, "python")
    rebuilt, _ = apply_manual_skills(
        original, load_manual_skills(profile / "manual_skills.json")
    )
    rebuilt, _ = replay_edits(rebuilt, load_edits(profile))
    assert any(s.name == "Python" for bucket in rebuilt.skills.values() for s in bucket)
    save_facts(rebuilt, profile / "facts.json")
    _apply(
        profile,
        _stage(profile, [_change(entity="skill", operation="delete", target_id="sk1")]),
    )
    add_skill(profile, "Python", "hard")
    rebuilt, _ = apply_manual_skills(
        original, load_manual_skills(profile / "manual_skills.json")
    )
    rebuilt, _ = replay_edits(rebuilt, load_edits(profile))
    assert any(s.name == "Python" for bucket in rebuilt.skills.values() for s in bucket)


def test_message_turn_stages_changes_without_mutating_profile(profile):
    from test_profile_coach_service import FakeAgent, FakeReporter

    create_session(
        profile,
        "s1",
        [CoachTopic(id="t1", gap="Profile")],
        CoachTurnRecord(role="coach", kind="question", text="First?", topic_id="t1"),
    )
    change = _change(
        entity="profile", operation="update", values={"summary": "Backend engineer"}
    )
    view = run_message_turn(
        FakeReporter(),
        profile_dir=profile,
        session_id="s1",
        message="Please make this change",
        coach_agent=FakeAgent("Review the draft."),
        formatter_agent=FakeAgent(
            CoachTurn(
                message="Review the draft.",
                action="changes",
                profile_changes=ProfileChangeSet(title="Summary", changes=[change]),
            )
        ),
    )
    assert _facts(profile).summary is None
    assert view["changeDrafts"][0]["status"] == "pending"
    assert view["turns"][-1]["kind"] == "profile_changes"


def test_library_rename_of_conversation_skill_survives_rebuild(profile):
    from resume_tailor_harness.profile.manual_skills import (
        apply_manual_skills,
        load_manual_skills,
    )
    from resume_tailor_harness.services.profile_skills import update_skill

    original = _facts(profile)
    _apply(
        profile,
        _stage(
            profile,
            [
                _change(
                    entity="skill",
                    operation="create",
                    values={"name": "Rust", "category": "hard"},
                )
            ],
        ),
    )
    update_skill(profile, "rust", "Rust programming", [], "hard")
    rebuilt, _ = apply_manual_skills(
        original, load_manual_skills(profile / "manual_skills.json")
    )
    rebuilt, _ = replay_edits(rebuilt, load_edits(profile))
    names = {s.name for bucket in rebuilt.skills.values() for s in bucket}
    assert "Rust programming" in names and "Rust" not in names


def test_library_restore_overrides_older_conversation_deletion(profile):
    from resume_tailor_harness.services.profile_skills import (
        delete_skill,
        restore_skill,
    )

    original = _facts(profile)
    _apply(
        profile,
        _stage(
            profile,
            [
                _change(
                    entity="skill",
                    operation="create",
                    values={"name": "Rust", "category": "hard"},
                )
            ],
        ),
    )
    rust = next(
        s
        for bucket in _facts(profile).skills.values()
        for s in bucket
        if s.name == "Rust"
    )
    delete_skill(profile, "rust")
    restore_skill(profile, "rust")
    _apply(
        profile,
        _stage(
            profile,
            [
                _change(
                    entity="skill",
                    operation="delete",
                    target_id=rust.id,
                )
            ],
        ),
    )
    # Re-adding and removing through the library must retain a restorable snapshot.
    from resume_tailor_harness.services.profile_skills import add_skill

    add_skill(profile, "Rust", "hard")
    delete_skill(profile, "rust")
    restore_skill(profile, "rust")
    rebuilt, _ = replay_edits(original, load_edits(profile))
    assert any(s.name == "Rust" for bucket in rebuilt.skills.values() for s in bucket)


def test_conversation_categories_and_moves_are_visible_in_skill_library(profile):
    from resume_tailor_harness.profile.group_corrections import (
        corrections_path,
        load_group_corrections,
    )
    from resume_tailor_harness.profile.matrix import build_decorated_matrix
    from resume_tailor_harness.services.profile_groups import edit_organization

    created = edit_organization(profile, "category", label="My languages")
    key = next(
        k for k, v in created.category_catalog().items() if v.label == "My languages"
    )
    _apply(
        profile,
        _stage(
            profile,
            [
                _change(
                    entity="skill",
                    operation="update",
                    target_id="sk1",
                    category=key,
                )
            ],
        ),
    )
    organization = load_group_corrections(corrections_path(profile))
    row = next(
        r
        for r in build_decorated_matrix(profile, _facts(profile)).rows
        if r.display == "Python"
    )
    assert row.group is not None
    assert organization.group_catalog()[row.group].category == key
    _apply(
        profile,
        _stage(
            profile,
            [
                _change(
                    entity="skill_category",
                    operation="update",
                    target_id=key,
                    values={"name": "Languages"},
                )
            ],
        ),
    )
    assert (
        load_group_corrections(corrections_path(profile)).category_catalog()[key].label
        == "Languages"
    )


def test_library_category_edit_invalidates_pending_conversation_draft(profile):
    from resume_tailor_harness.services.profile_groups import edit_organization

    draft = _stage(
        profile,
        [
            _change(
                entity="profile", operation="update", values={"summary": "New summary"}
            )
        ],
    )
    edit_organization(profile, "category", label="New category")
    with pytest.raises(StaleProfileDraft):
        _apply(profile, draft)


def test_skill_only_rebuild_keeps_conversation_suppression(profile, monkeypatch):
    import json
    from types import SimpleNamespace
    from resume_tailor_harness.services import profile_skill_build as build
    from resume_tailor_harness.services.profile_skills import add_skill
    from resume_tailor_harness.taxonomy.groups import (
        SkillGroupAssignment,
        SkillGroupAssignments,
    )

    added = add_skill(profile, "Rust", "hard")
    _apply(
        profile,
        _stage(
            profile, [_change(entity="skill", operation="delete", target_id=added.id)]
        ),
    )

    class Classifier:
        def run(self, prompt):
            return SimpleNamespace(
                content=SkillGroupAssignments(
                    assignments=[
                        SkillGroupAssignment(token=token, group="other")
                        for token in json.loads(prompt)["skills"]
                    ]
                )
            )

    monkeypatch.setattr(build, "build_profile_group_agent", lambda: Classifier())
    build.rebuild_profile_skills(profile, reclassify_only=True)
    assert all(
        s.name != "Rust" for bucket in _facts(profile).skills.values() for s in bucket
    )


def test_category_preview_is_read_only_and_approval_uses_the_reviewed_group(profile):
    from resume_tailor_harness.profile.group_corrections import (
        corrections_path,
        load_group_corrections,
    )

    _, _, preview = make_profile_tools(profile, user_text="Please make this change")
    proposal = ProfileChangeSet(
        title="Move Python",
        changes=[
            _change(
                entity="skill",
                operation="update",
                target_id="sk1",
                category="technical",
            )
        ],
    )
    before = _bytes(profile)
    assert preview(proposal)["valid"]
    assert _bytes(profile) == before
    draft = _stage(profile, proposal.changes)
    group = draft.changes[0].organization_group
    _apply(profile, draft)
    organization = load_group_corrections(corrections_path(profile))
    assert organization.corrections["python"].group == group
    inspect, _, _ = make_profile_tools(profile)
    assert any(
        row["id"] == "technical" for row in inspect("skill_categories")["records"]
    )
    assert (
        next(row for row in inspect("skills")["records"] if row["name"] == "Python")[
            "display_category"
        ]
        == "technical"
    )


def test_conversation_only_build_cleans_skills_without_growing_suppressions(tmp_path):
    from resume_tailor_harness.profile.manual_skills import load_manual_skills
    from resume_tailor_harness.services.profile_build import run_corpus_build

    _apply(
        tmp_path,
        _stage(
            tmp_path,
            [
                _change(
                    entity="profile",
                    operation="create",
                    values={"contact": {"name": "Ada"}},
                )
            ],
        ),
    )
    _apply(
        tmp_path,
        _stage(
            tmp_path,
            [
                _change(
                    entity="skill",
                    operation="create",
                    values={"name": "Willingness to travel", "category": "hard"},
                )
            ],
        ),
    )
    for _ in range(2):
        report = run_corpus_build(
            profile_dir=tmp_path,
            facts_out=tmp_path / "facts.json",
            github_username=None,
        )
        assert report["matrixRows"] == 0
        assert len(load_manual_skills(tmp_path / "manual_skills.json").entries) == 1
