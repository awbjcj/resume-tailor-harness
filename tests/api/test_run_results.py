"""Completed work has a durable, current and strictly local continuation."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.discovery.scout_store import ScoutSession
from resume_tailor_harness.services.run_completions import record_run_completion
from resume_tailor_harness.sessions.store import SessionStore
from resume_tailor_harness.tracking.tables import (
    Application,
    CoverLetter,
    Job,
    ResumeVersion,
    RunCompletionTarget,
)


@pytest.fixture
def app_client(tmp_path):
    app = create_app(
        db_url="sqlite://", data_dir=tmp_path / "data", config_dir=tmp_path / "config"
    )
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            job = Job(source="manual", title="Engineer", status="approved")
            session.add(job)
            session.commit()
            session.refresh(job)
            assert job.id is not None
            job_id = job.id
        yield app, client, job_id


def record(app, **values):
    with Session(app.state.engine) as session:
        record_run_completion(
            session,
            run_id="targeted",
            kind="tailor",
            label="Completed",
            status="succeeded",
            error=None,
            completed_at=datetime.now(timezone.utc),
            **values,
        )


def test_terminal_hook_captures_bulk_result_ids_and_ignores_arbitrary_metadata(
    app_client,
):
    app, client, job_id = app_client
    run_id = app.state.run_manager.submit(
        "tailor",
        lambda _reporter: {
            "jobs": [{"jobId": job_id, "versionCount": 1}],
            "url": "https://attacker.invalid/result",
        },
        meta={
            "jobIds": [job_id, True, -3, "../../private", None],
            "path": "D:/private/token.txt",
            "token": "private-secret",
            "resultHref": "https://attacker.invalid",
        },
    )
    for future in list(app.state.run_manager._futures.values()):
        future.result(timeout=2)
    with Session(app.state.engine) as session:
        target = session.get(RunCompletionTarget, run_id)
        assert target is not None and target.job_ids_json == [job_id]
        serialized = target.model_dump_json()
        assert "attacker" not in serialized and "private" not in serialized
    with patch.object(app.state.run_manager, "get", return_value=None):
        [row] = client.get("/api/run-completions").json()
        assert row["resultHref"] == f"/pipeline?job={job_id}&tab=resumes"
        assert row["resultAvailable"] is True
        assert (
            client.get(f"/api/run-completions/by-run/{run_id}").json()["resultHref"]
            == row["resultHref"]
        )
    assert client.get("/api/run-completions/by-run/unknown").status_code == 404


def test_job_result_uses_current_submission_and_preserves_read_state(app_client):
    app, client, job_id = app_client
    record(app, meta={"jobId": job_id})
    initial = client.get("/api/run-completions/by-run/targeted").json()
    assert initial["resultHref"] == f"/pipeline?job={job_id}&tab=resumes"
    with Session(app.state.engine) as session:
        session.add(Application(job_id=job_id, status="submitted"))
        session.commit()
    for _ in range(2):
        [row] = client.get("/api/run-completions").json()
        assert row["resultHref"] == f"/pipeline?job={job_id}&tab=tracking"
        assert row["readAt"] is None
    marked = client.post(f"/api/run-completions/{initial['id']}/read").json()
    assert (
        marked["resultHref"] == f"/pipeline?job={job_id}&tab=tracking"
        and marked["readAt"] is not None
    )
    with Session(app.state.engine) as session:
        assert len(session.exec(select(Application)).all()) == 1


def test_revision_uses_created_artifact_and_deleted_result_has_safe_fallback(
    app_client,
):
    app, client, job_id = app_client
    with Session(app.state.engine) as session:
        parent = ResumeVersion(job_id=job_id, fact_check_passed=True)
        child = ResumeVersion(job_id=job_id, fact_check_passed=True, origin="revision")
        session.add_all([parent, child])
        session.commit()
        session.refresh(parent)
        session.refresh(child)
        parent_id, child_id = parent.id, child.id
        record_run_completion(
            session,
            run_id="revision",
            kind="revise",
            label="Done",
            status="succeeded",
            error=None,
            completed_at=datetime.now(timezone.utc),
            meta={"versionId": parent_id, "jobId": job_id},
            result={"versionId": child_id, "jobId": job_id},
        )
        target = session.get(RunCompletionTarget, "revision")
        assert target is not None and target.resume_version_id == child_id
        session.delete(child)
        session.commit()
    [row] = client.get("/api/run-completions").json()
    assert row["resultAvailable"] is False
    assert row["resultHref"] == f"/pipeline?job={job_id}&tab=resumes"
    with Session(app.state.engine) as session:
        job = session.get(Job, job_id)
        assert job is not None
        session.delete(job)
        session.commit()
    [row] = client.get("/api/run-completions").json()
    assert row["resultAvailable"] is False and row["resultHref"] == "/pipeline"


def test_session_target_is_exact_and_deleted_or_invalid_sessions_fall_back(app_client):
    app, client, _ = app_client
    store = SessionStore(ScoutSession, label="scout")
    root = app.state.data_dir / "scout"
    store.write(root, {"session_id": "earlier-session", "goal": "Previous research"})
    with Session(app.state.engine) as session:
        for run_id, session_id in (
            ("exact", "earlier-session"),
            ("unsafe", "../secret"),
        ):
            record_run_completion(
                session,
                run_id=run_id,
                kind="scout-turn",
                label="Failed",
                status="failed",
                error="Unavailable",
                completed_at=datetime.now(timezone.utc),
                meta={"sessionId": session_id, "url": "https://attacker.invalid"},
            )
    exact = client.get("/api/run-completions/by-run/exact").json()
    assert exact["resultHref"] == "/scout?session=earlier-session"
    assert exact["resultAvailable"] is False
    unsafe = client.get("/api/run-completions/by-run/unsafe").json()
    assert unsafe["resultHref"] == "/scout"
    with Session(app.state.engine) as session:
        assert session.get(RunCompletionTarget, "unsafe") is None
    store.delete(root, "earlier-session")
    assert (
        client.get("/api/run-completions/by-run/exact").json()["resultHref"] == "/scout"
    )


def test_repeated_callback_does_not_replace_a_durable_target_or_restore_cleared_history(
    app_client,
):
    app, client, job_id = app_client
    record(app, meta={"jobId": job_id})
    assert client.delete("/api/run-completions").json() == {"cleared": 1}
    record(app, meta={"jobId": 999})
    assert client.get("/api/run-completions").json() == []
    with Session(app.state.engine) as session:
        target = session.get(RunCompletionTarget, "targeted")
        assert target is not None and target.job_ids_json == [job_id]


@pytest.mark.parametrize(
    "kind, href",
    [
        ("profile-build", "/profile"),
        ("tailor", "/pipeline"),
        ("gmailSync", "/settings/notifications"),
        ("unknown-legacy", "/"),
    ],
)
def test_legacy_history_falls_back_to_its_workspace(app_client, kind, href):
    app, client, _ = app_client
    with Session(app.state.engine) as session:
        record_run_completion(
            session,
            run_id="legacy",
            kind=kind,
            label="Done",
            status="succeeded",
            error=None,
            completed_at=datetime.now(timezone.utc),
        )
    [row] = client.get("/api/run-completions").json()
    assert row["resultHref"] == href and row["resultAvailable"] is False


def test_target_survives_restart(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'workspace.db').as_posix()}"
    params = {
        "db_url": db_url,
        "data_dir": tmp_path / "data",
        "config_dir": tmp_path / "config",
    }
    first = create_app(**params)
    with TestClient(first):
        with Session(first.state.engine) as session:
            job = Job(source="manual", status="approved")
            session.add(job)
            session.commit()
            session.refresh(job)
            job_id = job.id
        run_id = first.state.run_manager.submit(
            "tailor", lambda _reporter: {"jobs": [{"jobId": job_id}]}
        )
        for future in list(first.state.run_manager._futures.values()):
            future.result(timeout=2)
    with TestClient(create_app(**params)) as client:
        [row] = client.get("/api/run-completions").json()
        assert row["runId"] == run_id
        assert row["resultAvailable"] is True
        assert row["resultHref"] == f"/pipeline?job={job_id}&tab=resumes"


def test_deleted_job_id_cannot_redirect_history_to_a_new_job(app_client):
    app, client, job_id = app_client
    record(app, meta={"jobId": job_id})
    with Session(app.state.engine) as session:
        job = session.get(Job, job_id)
        assert job is not None
        session.delete(job)
        session.commit()
        replacement = Job(
            source="manual",
            status="approved",
            title="Unrelated replacement",
        )
        session.add(replacement)
        session.commit()
        assert replacement.id == job_id  # SQLite reuses the deleted highest ID.
    result = client.get("/api/run-completions/by-run/targeted").json()
    assert result["resultHref"] == "/pipeline"
    assert result["resultAvailable"] is False


@pytest.mark.parametrize(
    "model, key", [(ResumeVersion, "versionId"), (CoverLetter, "coverLetterId")]
)
def test_deleted_artifact_id_cannot_redirect_history_to_a_replacement(
    app_client, model, key
):
    app, client, job_id = app_client
    with Session(app.state.engine) as session:
        other = Job(source="manual", status="approved", title="Other job")
        session.add(other)
        original = model(job_id=job_id, fact_check_passed=True)
        session.add(original)
        session.commit()
        artifact_id = original.id
        record(app, meta={"jobId": job_id}, result={key: artifact_id})
        session.delete(original)
        session.commit()
        # An imported row may reuse a historical ID even on databases whose
        # normal allocator now assigns increasing resume IDs.
        replacement = model(
            id=artifact_id,
            job_id=other.id,
            fact_check_passed=True,
        )
        session.add(replacement)
        session.commit()
        assert replacement.id == artifact_id
    result = client.get("/api/run-completions/by-run/targeted").json()
    assert result["resultHref"] == f"/pipeline?job={job_id}&tab=resumes"
    assert result["resultAvailable"] is False
