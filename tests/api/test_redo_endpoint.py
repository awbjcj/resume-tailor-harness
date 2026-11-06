from contextlib import contextmanager
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.routers import runs as runs_router
from resume_tailor_harness.services import redo, redo_versions
from resume_tailor_harness.tailor.service import TailorOutcome
from resume_tailor_harness.tracking.repository import save_job, save_resume_version
from resume_tailor_harness.tracking.tables import Application, Job, ResumeVersion


def _client() -> TestClient:
    # In-memory sqlite keeps create_app in single-tenant mode (no admin
    # bootstrap / session auth), matching every other plain API test.
    return TestClient(create_app(db_url="sqlite://"))


def test_redo_rejects_empty_job_ids():
    with _client() as client:
        response = client.post("/api/redo", json={"jobIds": [], "stages": ["tailor"]})
    assert response.status_code == 422


def test_redo_rejects_empty_stages():
    with _client() as client:
        response = client.post("/api/redo", json={"jobIds": [1], "stages": []})
    assert response.status_code == 422


def test_redo_rejects_an_unknown_stage():
    with _client() as client:
        response = client.post(
            "/api/redo", json={"jobIds": [1], "stages": ["teleport"]}
        )
    assert response.status_code == 422


def test_redo_requires_tailoring_for_version_removal():
    with _client() as client:
        response = client.post(
            "/api/redo",
            json={"jobIds": [1], "stages": ["render"], "removePreviousVersions": True},
        )
    assert response.status_code == 422


@pytest.mark.parametrize("invalid_id", [True, 0, 2**63])
def test_redo_rejects_invalid_ids_before_the_cleanup_query(invalid_id):
    with _client() as client:
        response = client.post(
            "/api/redo",
            json={
                "jobIds": [invalid_id],
                "stages": ["tailor"],
                "removePreviousVersions": True,
            },
        )
    assert response.status_code == 422


def test_redo_dedupes_repeated_ids_and_stages():
    from resume_tailor_harness.api.schemas.runs import RedoParams

    params = RedoParams(job_ids=[3, 3, 1], stages=["tailor", "tailor"])

    assert params.job_ids == [3, 1]  # order preserved, duplicates dropped
    assert params.stages == ["tailor"]


def test_redo_returns_202_with_a_run():
    with _client() as client:
        response = client.post("/api/redo", json={"jobIds": [1], "stages": ["tailor"]})
    assert response.status_code == 202
    assert response.json()["kind"] == "redo"


def test_redo_receipt_names_replacement_and_removed_versions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(db_url="sqlite://", data_dir=tmp_path / "data")
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            job = save_job(session, Job(source="manual", status="tailored"))
            assert job.id is not None
            job_id = job.id
            old = save_resume_version(session, ResumeVersion(job_id=job_id))
            old_id = old.id
            session.add(Application(job_id=job_id, status="submitted"))
            session.commit()

        def tailor(session, **_kwargs):
            new = save_resume_version(
                session, ResumeVersion(job_id=job_id, fact_check_passed=True, attempt=1)
            )
            return TailorOutcome(versions={job_id: [new]})

        monkeypatch.setattr(redo, "tailor", tailor)
        response = client.post(
            "/api/redo",
            json={
                "jobIds": [job_id],
                "stages": ["tailor"],
                "removePreviousVersions": True,
            },
        )
        assert response.status_code == 202
        run_id = response.json()["runId"]
        for future in list(app.state.run_manager._futures.values()):
            future.result(timeout=5)

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["state"] == "done"
        [outcome] = run["result"]["outcomes"]
        assert outcome["versionId"] == run["result"]["versionId"] != old_id
        assert outcome["removedVersionIds"] == [old_id]
        result = client.get(f"/api/run-completions/by-run/{run_id}").json()
        assert result["resultAvailable"]
        assert result["resultHref"] == f"/pipeline?job={job_id}&tab=resumes"


@pytest.mark.parametrize("after_commit", [False, True])
def test_redo_cancellation_preserves_only_committed_removals(
    tmp_path, monkeypatch, after_commit
):
    app = create_app(
        db_url=f"sqlite:///{(tmp_path / 'workspace.db').as_posix()}",
        data_dir=tmp_path / "data",
        runs_root=tmp_path / "runs",
        env_path=tmp_path / ".env",
    )
    tailored, cleanup_started, release = Event(), Event(), Event()
    workspace_write = redo_versions.workspace_write
    export = redo_versions.export_job_artifacts
    replacements: dict[int, int | None] = {}
    old: dict[int, int] = {}

    def tailor(session, **_kwargs):
        versions = {}
        for job_id in old:
            version = save_resume_version(
                session, ResumeVersion(job_id=job_id, fact_check_passed=True, attempt=1)
            )
            replacements[job_id] = version.id
            versions[job_id] = [version]
        tailored.set()
        if not after_commit:
            assert release.wait(5)
        return TailorOutcome(versions=versions)

    @contextmanager
    def cleanup_writer(session):
        if not after_commit:
            cleanup_started.set()
        with workspace_write(session):
            yield

    def cleanup_export(*args, **kwargs):
        if after_commit:
            cleanup_started.set()
            assert release.wait(5)
        return export(*args, **kwargs)

    monkeypatch.setattr(redo, "tailor", tailor)
    monkeypatch.setattr(redo_versions, "workspace_write", cleanup_writer)
    monkeypatch.setattr(redo_versions, "export_job_artifacts", cleanup_export)
    with TestClient(app) as client:
        engine = app.state.engine
        with Session(engine) as session:
            for _ in range(2):
                job = save_job(session, Job(source="manual", status="tailored"))
                assert job.id is not None
                version = save_resume_version(session, ResumeVersion(job_id=job.id))
                assert version.id is not None
                old[job.id] = version.id
        first, second = old
        response = client.post(
            "/api/redo",
            json={
                "jobIds": [first, second],
                "stages": ["tailor"],
                "removePreviousVersions": True,
            },
        )
        assert response.status_code == 202
        run_id = response.json()["runId"]
        try:
            assert tailored.wait(5)
            with Session(engine) as blocker:
                if not after_commit:
                    blocker.connection().exec_driver_sql("BEGIN IMMEDIATE")
                    release.set()
                assert cleanup_started.wait(5)
                assert (blocker.get(ResumeVersion, old[first]) is None) is after_commit
                cancelled = client.post(f"/api/runs/{run_id}/cancel")
                assert cancelled.status_code == 200
        finally:
            release.set()
            for future in list(app.state.run_manager._futures.values()):
                future.result(timeout=5)

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["state"] == "cancelled"
        with Session(engine) as session:
            assert (session.get(ResumeVersion, old[first]) is None) is after_commit
            assert session.get(ResumeVersion, old[second]) is not None
        if after_commit:
            [outcome] = run["result"]["outcomes"]
            assert outcome["versionId"] == replacements[first]
            assert outcome["removedVersionIds"] == [old[first]]
        else:
            assert run["result"] is None


def test_redo_cleanup_conflicts_with_active_revision(tmp_path, monkeypatch):
    app = create_app(db_url="sqlite://", data_dir=tmp_path / "data")
    release = Event()

    def revise(*_args, **_kwargs):
        assert release.wait(5)
        return None

    monkeypatch.setattr(runs_router, "revise_resume_version", revise)
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            job_id = save_job(session, Job(source="manual")).id
            assert job_id is not None
            old_id = save_resume_version(session, ResumeVersion(job_id=job_id)).id
        first = client.post(
            f"/api/resume-versions/{old_id}/revise", json={"instruction": "Shorter"}
        )
        assert first.status_code == 202
        try:
            response = client.post(
                "/api/redo",
                json={
                    "jobIds": [job_id],
                    "stages": ["tailor"],
                    "removePreviousVersions": True,
                },
            )
            assert response.status_code == 409
            assert response.json()["error"]["details"]["runId"] == first.json()["runId"]
        finally:
            release.set()
            for future in list(app.state.run_manager._futures.values()):
                future.result(timeout=5)
