import json

import pytest
from sqlmodel import Session, select

from resume_tailor_harness.api.runs.manager import RunCancelled
from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.models.profile import Contact, ProfileFacts, Skill
from resume_tailor_harness.models.resume import ResumeContent, TailoredSkill
from resume_tailor_harness.models.review import ReviewCritique
from resume_tailor_harness.profile.store import save_facts
from resume_tailor_harness.progress import ProgressReporter
from resume_tailor_harness.services import external_tailoring as service
from resume_tailor_harness.tailor.review_config import ReviewConfig, ReviewerSpec
from resume_tailor_harness.tracking.tables import Job, ResumeVersion


@pytest.fixture
def external_case(tmp_path, monkeypatch):
    engine = make_engine("sqlite://")
    init_db(engine)
    facts = ProfileFacts(
        contact=Contact(name="Applicant"),
        skills={"Languages": [Skill(id="python", name="Python")]},
    )
    path = save_facts(facts, tmp_path / "facts.json")
    config = ReviewConfig(reviewers=[ReviewerSpec(name="fact-check", gate=True)])
    monkeypatch.setattr(service, "load_review_config", lambda _: config)
    monkeypatch.setattr(service, "build_reviewers", lambda *a, **kw: {})
    from resume_tailor_harness.render.export import export_job_artifacts

    monkeypatch.setattr(
        service,
        "export_job_artifacts",
        lambda session, job_id: export_job_artifacts(
            session, job_id, tmp_path / "exports"
        ),
    )
    monkeypatch.setattr(
        service,
        "run_panel",
        lambda *a: [ReviewCritique(reviewer="fact-check", score=100, passed=True)],
    )
    with Session(engine) as session:
        job = Job(source="manual", jd_text="Write Python", status="rendered")
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.id is not None
        content = ResumeContent(
            contact=facts.contact,
            skills={"Languages": [TailoredSkill(name="Python", provenance="python")]},
        )
        revision = service.load_context(session, job.id, path)[2]
        yield session, job.id, path, content, revision, facts, config
    engine.dispose()


def test_external_submission_appends_reviewed_version_without_regressing(external_case):
    session, job_id, path, content, revision, _, _ = external_case
    result = service.submit_draft(session, job_id, path, content, revision, "codex")
    assert result["passed"] and result["versionId"]
    version = session.get(ResumeVersion, result["versionId"])
    assert version.origin == "external" and version.fact_check_passed
    assert version.gate_reviewers_json == ["fact-check"]
    manifest_path = next((path.parent / "exports").glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert str(version.id) in json.dumps(manifest)
    assert (
        manifest_path.parent / f"resume-v{version.id}-external.content.json"
    ).is_file()
    assert session.get(Job, job_id).status == "rendered"
    again = service.submit_draft(session, job_id, path, content, revision, "pi")
    assert again["versionId"] != result["versionId"]
    assert session.get(ResumeVersion, again["versionId"]).attempt == version.attempt + 1


@pytest.mark.parametrize("change", ["citation", "number", "skill"])
def test_deterministic_failures_never_call_models_or_save(
    external_case, monkeypatch, change
):
    session, job_id, path, content, revision, _, _ = external_case

    def unexpected(*a):
        pytest.fail("A deterministic failure must not spend model calls")

    monkeypatch.setattr(service, "run_panel", unexpected)
    if change == "citation":
        content.skills["Languages"][0].provenance = "invented"
    elif change == "number":
        content.summary = "Improved efficiency by 95%"
        content.summary_provenance = ["python"]
    else:
        content.skills["Languages"][0].name = "Python / Kubernetes"
    preflight = service.validate_draft(session, job_id, path, content, revision)
    assert not preflight["valid"]
    result = service.submit_draft(session, job_id, path, content, revision, "test")
    assert not result["passed"] and result["versionId"] is None
    assert not session.exec(select(ResumeVersion)).all()


def test_identity_changes_rejected(external_case):
    session, job_id, path, content, revision, _, _ = external_case
    content.contact = Contact(name="Invented person")
    with pytest.raises(service.ExternalTailoringError, match="verbatim"):
        service.validate_draft(session, job_id, path, content, revision)


@pytest.mark.parametrize("during_review", [False, True])
def test_stale_context_rejected_before_and_after_review(
    external_case, monkeypatch, during_review
):
    session, job_id, path, content, revision, facts, _ = external_case

    def mutate(*a):
        save_facts(facts.model_copy(update={"summary": "New evidence"}), path)
        return [ReviewCritique(reviewer="fact-check", score=100, passed=True)]

    if during_review:
        monkeypatch.setattr(service, "run_panel", mutate)
    else:
        mutate()
    with pytest.raises(service.ExternalTailoringError) as exc:
        service.submit_draft(session, job_id, path, content, revision, "test")
    assert exc.value.code == "CONTEXT_STALE"
    assert not session.exec(select(ResumeVersion)).all()


def test_panel_failure_does_not_save(external_case, monkeypatch):
    session, job_id, path, content, revision, _, _ = external_case
    monkeypatch.setattr(
        service,
        "run_panel",
        lambda *a: [ReviewCritique(reviewer="fact-check", score=0, passed=False)],
    )
    assert not service.submit_draft(session, job_id, path, content, revision, "test")[
        "passed"
    ]
    assert not session.exec(select(ResumeVersion)).all()


def test_fact_check_cannot_be_disabled(external_case):
    session, job_id, path, content, revision, _, config = external_case
    config.reviewers = []
    with pytest.raises(service.ExternalTailoringError) as exc:
        service.submit_draft(session, job_id, path, content, revision, "test")
    assert exc.value.code == "REVIEW_REQUIRED"


def test_cancellation_before_persistence_does_not_save(external_case, monkeypatch):
    session, job_id, path, content, revision, _, _ = external_case

    def cancelled():
        raise RunCancelled()

    reporter = ProgressReporter("tailor", root=path.parent / "progress")
    monkeypatch.setattr(reporter, "checkpoint", cancelled)
    with pytest.raises(RunCancelled):
        service.submit_draft(
            session,
            job_id,
            path,
            content,
            revision,
            "test",
            reporter=reporter,
        )
    assert not session.exec(select(ResumeVersion)).all()
