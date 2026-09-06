import pytest
from sqlmodel import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    Draft,
    JobFacts,
    Observation,
    OverridePatch,
    ValidationResult,
)
from resume_tailor_harness.discovery.scraper.store import RevisionConflict, ScrapeStore


def example_draft():
    return Draft(
        source_id="board",
        url="https://example.com/jobs",
        plan=BoardPlan(card_selector="article", detail_mode="inline"),
        state="validated",
        validation=ValidationResult(valid=True),
    )


def test_restart_preserves_explicit_unknown_and_removal_history(tmp_path):
    url = f"sqlite:///{tmp_path / 'workspace.db'}"
    engine = make_engine(url)
    init_db(engine)
    observation = Observation(
        source_id="board",
        revision=1,
        job_key="job-1",
        facts=JobFacts(source_url="https://example.com/jobs/1", remote_policy="remote"),
    )
    with Session(engine) as session:
        store = ScrapeStore(session)
        store.save_draft(example_draft())
        store.save_observation(observation)
        assert (
            store.set_override(
                "job-1",
                OverridePatch(field="remote_policy", value=None, expected_revision=0),
            )
            == 1
        )
        session.commit()
    engine.dispose()
    engine = make_engine(url)
    with Session(engine) as session:
        store = ScrapeStore(session)
        assert store.effective_facts(observation).remote_policy is None
        assert store.remove_override("job-1", "remote_policy", 1) == 2
        assert store.effective_facts(observation).remote_policy == "remote"
        assert len(store.override_history("job-1")) == 2


def test_stale_edit_and_approval_rejected_and_retry_is_idempotent(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'workspace.db'}")
    init_db(engine)
    draft = example_draft()
    with Session(engine) as session:
        store = ScrapeStore(session)
        draft = store.save_draft(draft)
        session.commit()
    with Session(engine) as session:
        store = ScrapeStore(session)
        approved = store.approve(draft.id, draft.revision)
        session.commit()
        assert store.approve(draft.id, draft.revision) == approved
        with pytest.raises(RevisionConflict):
            store.approve(draft.id, draft.revision - 1)
        with pytest.raises(RevisionConflict):
            store.save_draft(
                draft.model_copy(update={"url": "https://example.com/other"})
            )


def test_unvalidated_draft_cannot_be_approved():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        draft = store.save_draft(Draft(source_id="board", url="https://example.com"))
        with pytest.raises(ValueError, match="validated"):
            store.approve(draft.id, draft.revision)


def test_invalid_override_does_not_replace_valid_value():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        with pytest.raises(ValueError):
            store.set_override(
                "job-1",
                OverridePatch(
                    field="remote_policy", value="maybe", expected_revision=0
                ),
            )
        assert store.override_history("job-1") == []


def test_rollback_does_not_leave_approved_revision():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        draft = store.save_draft(example_draft())
        session.commit()
        store.approve(draft.id, draft.revision)
        session.rollback()
        assert store.get_draft(draft.id).state == "validated"
        assert store.list_sources() == []


def test_old_draft_cannot_replace_a_newly_approved_source():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        first = store.save_draft(example_draft())
        stale = store.save_draft(example_draft())
        store.approve(first.id, 0)
        session.commit()
        with pytest.raises(RevisionConflict, match="source"):
            store.approve(stale.id, 0)


def test_value_overrides_cannot_rewrite_posting_identity():
    from resume_tailor_harness.discovery.scraper.contracts import OverridePatch

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="identity"):
            ScrapeStore(session).set_override(
                "one",
                OverridePatch(
                    field="source_url",
                    value="https://elsewhere.example/",
                    expected_revision=0,
                ),
            )


def test_changed_source_value_under_override_is_retained_as_conflict():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        old = Observation(
            source_id="board",
            revision=1,
            job_key="one",
            accepted=True,
            facts=JobFacts(
                source_url="https://example.com/1",
                title="Engineer",
                jd_text="Build systems",
                remote_policy="remote",
            ),
        )
        store.save_observation(old)
        store.set_override(
            "one", OverridePatch(field="remote_policy", value=None, expected_revision=0)
        )
        new = old.model_copy(deep=True, update={"id": "new"})
        new.facts.remote_policy = "hybrid"
        store.save_observation(new)
        assert not new.accepted
        assert any(
            item.field == "remote_policy" and item.kind == "conflict"
            for item in new.issues
        )
        assert store.effective_facts(new).remote_policy is None
