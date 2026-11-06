import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from resume_tailor_harness.progress import ProgressReporter
from resume_tailor_harness.render.export import export_job_artifacts, job_dir
from resume_tailor_harness.services import redo
from resume_tailor_harness.services.errors import StageFailure, list_error_records
from resume_tailor_harness.tailor.service import TailorOutcome
from resume_tailor_harness.tracking.repository import (
    application_for_job,
    resume_versions_for_job,
    save_job,
    save_resume_version,
)
from resume_tailor_harness.tracking.tables import (
    Application,
    CoverLetter,
    Job,
    JobStatus,
    ResumeVersion,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as database:
        yield database


@pytest.fixture(autouse=True)
def _no_budget(monkeypatch):
    monkeypatch.setattr(redo, "enforce_active_budget", lambda: None)


def _rendered_job(session) -> Job:
    return save_job(
        session,
        Job(
            source="manual",
            jd_text="jd",
            company="Acme",
            title="Staff",
            status=JobStatus.rendered.value,
        ),
    )


def _version(session: Session, job_id: int, **values) -> ResumeVersion:
    return save_resume_version(session, ResumeVersion(job_id=job_id, **values))


def test_stages_run_in_pipeline_order_whatever_order_was_asked(session, monkeypatch):
    job = _rendered_job(session)
    assert job.id is not None
    seen: list[str] = []
    monkeypatch.setattr(redo, "_run_pull", lambda *a, **k: seen.append("pull") or [])
    monkeypatch.setattr(
        redo, "_run_extract", lambda *a, **k: seen.append("extract") or []
    )
    monkeypatch.setattr(
        redo, "_run_tailor", lambda *a, **k: seen.append("tailor") or []
    )

    redo.redo_jobs(session, job_ids=[job.id], stages=["tailor", "extract", "pull"])

    assert seen == ["pull", "extract", "tailor"]


def test_tailor_failure_is_recorded_as_a_job_error(session, monkeypatch):
    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    failure = StageFailure(
        error_type="ValueError", message="no match-plan agent", traceback_tail="tb"
    )
    monkeypatch.setattr(
        redo,
        "tailor",
        lambda *a, **k: TailorOutcome(versions={}, failures={job_id: failure}),
    )

    outcomes = redo.redo_jobs(session, job_ids=[job.id], stages=["tailor"])

    assert [o.status for o in outcomes] == ["failed"]
    records = list_error_records(session, "open")
    assert len(records) == 1
    assert records[0].kind == "job"
    assert records[0].source_label == f"job:{job.id}:tailor"


def test_tailor_failure_records_the_model_that_produced_it(session, monkeypatch):
    """The motivating case: when a re-tailor fails, the first question is which
    model produced it (see spec: 'model' is the resolved model id for extract
    and tailor)."""
    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    failure = StageFailure(error_type="ValueError", message="boom", traceback_tail="")
    monkeypatch.setattr(
        redo,
        "tailor",
        lambda *a, **k: TailorOutcome(
            versions={}, failures={job_id: failure}, model="openai:gpt-5"
        ),
    )

    redo.redo_jobs(session, job_ids=[job.id], stages=["tailor"])

    records = list_error_records(session, "open")
    assert records[0].details_json is not None
    assert records[0].details_json["model"] == "openai:gpt-5"


def test_tailor_success_resolves_an_earlier_failure(session, monkeypatch):
    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    failure = StageFailure(error_type="ValueError", message="boom", traceback_tail="")
    monkeypatch.setattr(
        redo,
        "tailor",
        lambda *a, **k: TailorOutcome(versions={}, failures={job_id: failure}),
    )
    redo.redo_jobs(session, job_ids=[job_id], stages=["tailor"])
    assert len(list_error_records(session, "open")) == 1

    monkeypatch.setattr(
        redo,
        "tailor",
        lambda *a, **k: TailorOutcome(versions={job_id: [_version(session, job_id)]}),
    )
    outcomes = redo.redo_jobs(session, job_ids=[job_id], stages=["tailor"])

    assert [o.status for o in outcomes] == ["ok"]
    assert list_error_records(session, "open") == []


def test_missing_job_is_skipped_not_fatal(session, monkeypatch):
    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    monkeypatch.setattr(
        redo,
        "tailor",
        lambda *a, **k: TailorOutcome(versions={job_id: [_version(session, job_id)]}),
    )

    outcomes = redo.redo_jobs(session, job_ids=[job_id, 9999], stages=["tailor"])

    statuses = {o.job_id: o.status for o in outcomes}
    assert statuses[job_id] == "ok"
    assert statuses[9999] == "skipped"


def test_render_skips_a_job_with_no_versions(session):
    job = _rendered_job(session)
    assert job.id is not None

    outcomes = redo.redo_jobs(session, job_ids=[job.id], stages=["render"])

    assert outcomes[0].status == "skipped"
    assert outcomes[0].detail == "no resume version"


def test_extract_stage_reports_the_real_per_job_outcome(session, monkeypatch):
    """run_extract/run_score silently skip a failed job internally; redo must
    not paper over that as a blanket 'ok' -- it should record and surface it,
    the same way pull and tailor already do."""
    good = _rendered_job(session)
    bad = _rendered_job(session)
    assert good.id is not None
    assert bad.id is not None
    failure = StageFailure(error_type="ValueError", message="boom", traceback_tail="")
    monkeypatch.setattr(redo, "load_search_config", lambda p: object())
    monkeypatch.setattr(redo, "load_facts", lambda p: object())
    monkeypatch.setattr(redo, "_skill_artifacts", lambda p, f: (None, None))
    monkeypatch.setattr(
        redo,
        "build_discovery_bundle",
        lambda: type(
            "B",
            (),
            {
                "extract": None,
                "fit": None,
                "canonicalizer": None,
                "industry_classifier": None,
            },
        )(),
    )
    monkeypatch.setattr(redo, "run_extract", lambda *a, **k: {bad.id: failure})

    def filter_successful(session, config, scope):
        assert scope.job_ids == {good.id}

    def score_successful(*args, scope, **kwargs):
        assert scope.job_ids == {good.id}
        return {}

    monkeypatch.setattr(redo, "run_filter", filter_successful)
    monkeypatch.setattr(redo, "run_score", score_successful)

    outcomes = redo.redo_jobs(session, job_ids=[good.id, bad.id], stages=["extract"])

    statuses = {o.job_id: o.status for o in outcomes}
    assert statuses[good.id] == "ok"
    assert statuses[bad.id] == "failed"
    records = list_error_records(session, "open")
    assert len(records) == 1
    assert records[0].source_label == f"job:{bad.id}:extract"


def test_redo_never_regresses_a_rendered_job(session, monkeypatch):
    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    monkeypatch.setattr(
        redo,
        "tailor",
        lambda *a, **k: TailorOutcome(versions={job_id: [_version(session, job_id)]}),
    )
    monkeypatch.setattr(redo, "_run_extract", lambda *a, **k: [])

    redo.redo_jobs(session, job_ids=[job_id], stages=["extract", "tailor"])

    session.refresh(job)
    assert job.status == JobStatus.rendered.value


@pytest.mark.parametrize("remove_previous", [False, True])
def test_redo_renders_its_own_attempt_and_only_removes_eligible_old_versions(
    session,
    monkeypatch,
    tmp_path,
    remove_previous,
):
    monkeypatch.chdir(tmp_path)
    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    selected_pdf = tmp_path / "selected.pdf"
    selected_pdf.write_bytes(b"selected PDF")
    old_pdf = tmp_path / "old.pdf"
    old_pdf.write_bytes(b"old PDF")
    selected = _version(session, job_id, pdf_path=str(selected_pdf))
    assert selected.id is not None
    selected_id = selected.id
    old = _version(session, job_id, pdf_path=str(old_pdf))
    shared = _version(session, job_id, pdf_path=str(selected_pdf))
    draft = _version(session, job_id)
    manual = _version(session, job_id, origin="revision")
    parent = _version(session, job_id)
    external = _version(session, job_id, origin="external", parent_version_id=parent.id)
    source = _version(session, job_id)
    # Selection changes made during tailoring also take precedence over cleanup.
    newly_selected = _version(session, job_id, fact_check_passed=True)
    newly_selected_id = newly_selected.id
    assert newly_selected_id is not None
    session.add(Application(job_id=job_id, resume_version_id=selected_id))
    session.add(CoverLetter(job_id=job_id, resume_version_id=source.id))
    session.commit()
    export = export_job_artifacts(session, job_id)
    assert export is not None
    removable_ids = {old.id, shared.id, draft.id}
    old_ids = {
        v.id for v in (selected, manual, parent, external, source, newly_selected)
    }

    def tailor(session, **_kwargs):
        job.title = "Updated title"
        save_job(session, job)
        first = _version(session, job_id, attempt=2, round=1)
        final = _version(session, job_id, attempt=2, round=2, fact_check_passed=True)
        _version(session, job_id, attempt=3)  # A separate author finishes later.
        return TailorOutcome(versions={job_id: [first, final]})

    rendered_ids = []

    def render(session, version_id):
        rendered_ids.append(version_id)
        version = session.get(ResumeVersion, version_id)
        assert version is not None and version.round == 2
        path = tmp_path / "replacement.pdf"
        path.write_bytes(b"replacement PDF")
        version.pdf_path = str(path)
        save_resume_version(session, version)
        from resume_tailor_harness.services.board import select_resume_version

        select_resume_version(session, job_id, newly_selected_id)
        return path

    monkeypatch.setattr(redo, "tailor", tailor)
    monkeypatch.setattr(redo, "render_resume_version", render)
    tailored, rendered = redo.redo_jobs(
        session,
        job_ids=[job_id],
        stages=["render", "tailor"],
        remove_previous_versions=remove_previous,
    )

    assert tailored.version is not None and rendered.version == tailored.version
    assert rendered_ids == [tailored.version.id]
    application = application_for_job(session, job_id)
    assert (
        application is not None and application.resume_version_id == newly_selected_id
    )
    assert selected_pdf.read_bytes() == b"selected PDF"
    assert old_pdf.exists() is not remove_previous
    assert set(rendered.removed_version_ids) == (
        removable_ids if remove_previous else set()
    )
    versions = resume_versions_for_job(session, job_id)
    assert {v.round for v in versions if v.attempt == 2} == {1, 2}
    assert len([v for v in versions if v.attempt == 3]) == 1
    assert {v.id for v in versions if v.attempt == 0} == (
        old_ids if remove_previous else old_ids | removable_ids
    )
    for version_id in removable_ids:
        assert (
            export / f"resume-v{version_id}-tailor.content.json"
        ).exists() is not remove_previous
    if remove_previous:
        old_manifest = json.loads((export / "manifest.json").read_text(encoding="utf-8"))
        assert {item["id"] for item in old_manifest["resumeVersions"]} == old_ids
        new_manifest = job_dir("output", job) / "manifest.json"
        assert {item["id"] for item in json.loads(new_manifest.read_text(encoding="utf-8"))["resumeVersions"]} == {
            v.id for v in versions
        }


@pytest.mark.parametrize("failure_stage", [None, "fact-lock", "render", "tailor"])
def test_redo_keeps_older_work_until_its_replacement_is_usable(
    session,
    monkeypatch,
    tmp_path,
    failure_stage,
):
    monkeypatch.chdir(tmp_path)
    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    existing_pdf = tmp_path / "existing.pdf"
    existing_pdf.write_bytes(b"old PDF")
    old_pdf_id = _version(session, job_id, pdf_path=str(existing_pdf)).id
    old_draft_id = _version(session, job_id).id

    def tailor(session, **kwargs):
        if failure_stage == "tailor":
            return TailorOutcome()
        return TailorOutcome(
            versions={
                job_id: [
                    _version(
                        session,
                        job_id,
                        attempt=1,
                        fact_check_passed=True,
                        critique_json=[{"reviewer": "provenance", "passed": False}]
                        if failure_stage == "fact-lock"
                        else None,
                    )
                ]
            }
        )

    def render(session, version_id):
        assert failure_stage == "render"
        raise ValueError("render failed")

    monkeypatch.setattr(redo, "tailor", tailor)
    monkeypatch.setattr(redo, "render_resume_version", render)
    outcomes = redo.redo_jobs(
        session,
        job_ids=[job_id],
        stages=["tailor", "render"]
        if failure_stage in {"tailor", "render"}
        else ["tailor"],
        remove_previous_versions=True,
    )
    ids = {v.id for v in resume_versions_for_job(session, job_id)}
    assert old_pdf_id in ids and existing_pdf.read_bytes() == b"old PDF"
    assert (old_draft_id in ids) is (failure_stage is not None)
    if failure_stage == "tailor":
        assert [o.status for o in outcomes] == ["failed", "skipped"]
    if failure_stage == "render":
        assert [o.status for o in outcomes] == ["ok", "failed"]


def test_redo_cancellation_before_cleanup_keeps_existing_versions(
    session, monkeypatch, tmp_path
):
    class CancelBeforeCleanup(ProgressReporter):
        def checkpoint(self) -> None:
            raise InterruptedError("cancelled")

    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    old = _version(session, job_id)
    monkeypatch.setattr(
        redo,
        "tailor",
        lambda *a, **k: TailorOutcome(
            versions={job_id: [_version(session, job_id, fact_check_passed=True)]}
        ),
    )

    with pytest.raises(InterruptedError, match="cancelled"):
        redo.redo_jobs(
            session,
            job_ids=[job_id],
            stages=["tailor"],
            remove_previous_versions=True,
            reporter=CancelBeforeCleanup("redo", root=tmp_path),
        )

    assert old in resume_versions_for_job(session, job_id)


def test_redo_skips_failed_dependencies_without_blocking_other_jobs(
    session, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    good_id = _rendered_job(session).id
    bad_id = _rendered_job(session).id
    assert good_id is not None and bad_id is not None
    good_old_id = _version(session, good_id).id
    bad_old_id = _version(session, bad_id).id

    def tailor(session, *, job_ids, **kwargs):
        assert job_ids == [good_id]
        return TailorOutcome(
            versions={good_id: [_version(session, good_id, fact_check_passed=True)]}
        )

    monkeypatch.setattr(
        redo,
        "_run_extract",
        lambda *args: [
            redo.StageOutcome(good_id, "extract", "ok"),
            redo.StageOutcome(bad_id, "extract", "failed", "extract failed"),
        ],
    )
    monkeypatch.setattr(redo, "tailor", tailor)

    outcomes = redo.redo_jobs(
        session,
        job_ids=[good_id, bad_id],
        stages=["extract", "tailor"],
        remove_previous_versions=True,
    )

    assert [(o.job_id, o.stage, o.status) for o in outcomes] == [
        (good_id, "extract", "ok"),
        (bad_id, "extract", "failed"),
        (good_id, "tailor", "ok"),
        (bad_id, "tailor", "skipped"),
    ]
    assert outcomes[2].removed_version_ids == (good_old_id,)
    assert [v.id for v in resume_versions_for_job(session, bad_id)] == [bad_old_id]


def test_render_only_keeps_application_target(session, monkeypatch):
    job = _rendered_job(session)
    assert job.id is not None
    job_id = job.id
    selected_id = _version(session, job_id).id
    _version(session, job_id)
    session.add(Application(job_id=job_id, resume_version_id=selected_id))
    session.commit()
    seen = []
    monkeypatch.setattr(
        redo,
        "render_resume_version",
        lambda _, vid: seen.append(vid) or Path("rendered.pdf"),
    )

    [outcome] = redo.redo_jobs(session, job_ids=[job_id], stages=["render"])

    assert seen == [selected_id]
    assert outcome.version is not None and outcome.version.id == selected_id
