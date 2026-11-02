"""Source publication is certified by successful builds, never file timestamps."""

from types import SimpleNamespace

import pytest

from resume_tailor_harness.models.profile import Contact, ProfileFacts
from resume_tailor_harness.profile.build import build_corpus_profile
from resume_tailor_harness.profile.conversation import (
    ProfileChange,
    ProfileChangeSet,
    prepare_changes,
)
from resume_tailor_harness.profile.corpus import add_source, doc_path, update_source
from resume_tailor_harness.profile.intake import add_note_source
from resume_tailor_harness.profile.publication import (
    PUBLICATION_NAME,
    load_publication,
    publication_status,
)
from resume_tailor_harness.profile.store import load_facts, save_facts
from resume_tailor_harness.services.profile_build import run_corpus_build
from resume_tailor_harness.services.profile_conversation import apply_workspace_draft


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    resume = tmp_path / "resume.txt"
    resume.write_text("Ada's original evidence", encoding="utf-8")
    primary = add_source(root, resume, primary=True)

    class Extractor:
        def run(self, prompt):
            return SimpleNamespace(content=ProfileFacts(contact=Contact(name="Ada")))

        async def arun(self, prompt):
            return self.run(prompt)

    def extract(profile_dir, **_kwargs):
        return build_corpus_profile(
            profile_dir, github_username=None, extractor_agent=Extractor()
        )

    monkeypatch.setattr(
        "resume_tailor_harness.profile.build.build_corpus_profile", extract
    )
    for module, name in (
        ("inference", "build_inference_agent"),
        ("merge", "build_bullet_dedup_agent"),
        ("synthesis", "build_synthesis_agent"),
        ("synthesis", "build_entailment_agent"),
        ("project_extractor", "build_project_extractor_agent"),
        ("aspect_classifier", "build_aspect_classifier_agent"),
    ):
        monkeypatch.setattr(
            f"resume_tailor_harness.profile.{module}.{name}", lambda: object()
        )
    return root, primary, extract


def _build(root):
    return run_corpus_build(
        profile_dir=root, facts_out=root / "facts.json", github_username=None
    )


def test_source_change_stays_pending_after_approved_direct_profile_edit(corpus):
    root, primary, _ = corpus
    _build(root)
    assert publication_status(root).freshness == "current"
    publication = (root / PUBLICATION_NAME).read_bytes()
    doc_path(root, primary).write_text("Updated source evidence", encoding="utf-8")

    request = "My summary is Platform engineer"
    draft = prepare_changes(
        root,
        ProfileChangeSet(
            title="Update summary",
            changes=[
                ProfileChange(
                    entity="profile",
                    operation="update",
                    values={"summary": "Platform engineer"},
                    quotes=[request],
                )
            ],
        ),
        request,
        source_ref="coach:test",
    )
    apply_workspace_draft(root, draft, request)

    assert load_facts(root / "facts.json").summary == "Platform engineer"
    assert (root / PUBLICATION_NAME).read_bytes() == publication
    status = publication_status(root)
    assert status.freshness == "refresh-needed"
    assert status.pending_source_count == 1


def test_evidence_added_after_extraction_remains_pending(corpus, monkeypatch):
    root, _, extract = corpus
    late_id = ""

    def extract_then_add(*args, **kwargs):
        nonlocal late_id
        facts, report = extract(*args, **kwargs)
        late_id = add_note_source(root, "Late evidence", "I shipped another project").id
        return facts, report

    monkeypatch.setattr(
        "resume_tailor_harness.profile.build.build_corpus_profile", extract_then_add
    )
    _build(root)
    publication = load_publication(root)
    assert publication is not None
    assert late_id not in publication.inputs.documents
    assert publication_status(root).pending_source_count == 1

    monkeypatch.setattr(
        "resume_tailor_harness.profile.build.build_corpus_profile", extract
    )
    _build(root)
    assert publication_status(root).freshness == "current"


def test_failed_publication_preserves_last_receipt_and_both_artifacts(
    corpus, monkeypatch
):
    root, primary, _ = corpus
    _build(root)
    names = ("facts.json", "matrix.json", PUBLICATION_NAME)
    before = {name: (root / name).read_bytes() for name in names}
    doc_path(root, primary).write_text("New evidence", encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise OSError("receipt cannot be written")

    monkeypatch.setattr(
        "resume_tailor_harness.services.profile_build.save_publication", fail
    )
    with pytest.raises(OSError, match="receipt cannot be written"):
        _build(root)
    assert {name: (root / name).read_bytes() for name in names} == before
    assert publication_status(root).freshness == "refresh-needed"


def test_interpretation_changes_and_legacy_profiles_do_not_claim_freshness(corpus):
    root, _, _ = corpus
    save_facts(ProfileFacts(contact=Contact(name="Legacy")), root / "facts.json")
    assert publication_status(root).freshness == "unknown"
    _build(root)
    note = add_note_source(root, "Evidence", "Built and maintained the project")
    _build(root)
    assert publication_status(root).freshness == "current"
    update_source(root, note.id, mode="synthesis", anchor="experience-1")
    assert publication_status(root).pending_source_count == 1


def test_stale_fragment_fallback_does_not_certify_changed_source(corpus, monkeypatch):
    root, _, _ = corpus
    note = add_note_source(root, "Evidence", "Previous evidence")
    _build(root)
    doc_path(root, note).write_text(
        "New evidence cannot be extracted", encoding="utf-8"
    )

    async def fail(*_args, **_kwargs):
        raise RuntimeError("extractor unavailable")

    monkeypatch.setattr(
        "resume_tailor_harness.profile.fragments.aextract_profile_facts", fail
    )
    report = _build(root)
    assert report["docStatus"][note.id].startswith("stale:")
    publication = load_publication(root)
    assert publication is not None and note.id not in publication.inputs.documents
    assert publication_status(root).freshness == "refresh-needed"


def test_profile_removal_retires_the_old_publication(corpus):
    root, _, _ = corpus
    _build(root)
    request = "Remove my profile"
    draft = prepare_changes(
        root,
        ProfileChangeSet(
            title="Remove profile",
            changes=[
                ProfileChange(entity="profile", operation="delete", quotes=[request])
            ],
        ),
        request,
        source_ref="coach:test",
    )
    apply_workspace_draft(root, draft, request)
    assert publication_status(root).freshness == "missing"
    assert not (root / PUBLICATION_NAME).exists()
    with pytest.raises(ValueError, match="removed"):
        _build(root)
