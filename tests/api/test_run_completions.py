from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.services.run_completions import record_run_completion


def _persisted_id(value: int | None) -> int:
    assert value is not None
    return value


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(
        db_url="sqlite://",
        config_dir=tmp_path / "config",
        env_path=tmp_path / ".env",
        data_dir=tmp_path / "data",
    )
    with TestClient(app) as client:
        yield app, client


def test_run_completion_history_and_read_state(app_client):
    app, client = app_client
    with Session(app.state.engine) as session:
        record_run_completion(
            session,
            run_id="run-1",
            kind="discover",
            label="Discovery",
            status="succeeded",
            error=None,
            completed_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )

    listed = client.get("/api/run-completions")
    assert listed.status_code == 200
    [row] = listed.json()
    assert row["runId"] == "run-1"
    assert row["readAt"] is None

    marked = client.post(f"/api/run-completions/{row['id']}/read")
    assert marked.status_code == 200
    assert marked.json()["readAt"] is not None
    assert client.get("/api/run-completions", params={"unread_only": True}).json() == []


def test_completed_app_run_is_persisted_by_terminal_hook(app_client):
    app, client = app_client
    run_id = app.state.run_manager.submit("discover", lambda _reporter: {"ok": True})
    for future in list(app.state.run_manager._futures.values()):
        future.result(timeout=2)

    [row] = client.get("/api/run-completions").json()
    assert row["runId"] == run_id
    assert row["status"] == "succeeded"


def test_clear_histories_independently_and_keep_new_operations(app_client):
    app, client = app_client
    with Session(app.state.engine) as session:
        record_run_completion(
            session,
            run_id="old",
            kind="pull",
            label="Pulled jobs",
            status="succeeded",
            error=None,
            completed_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
            logs=[
                {
                    "timestamp": "2026-08-29T00:00:00Z",
                    "message": "Pulled jobs",
                    "state": "done",
                }
            ],
        )
    [row] = client.get("/api/run-completions").json()
    assert (
        client.get(f"/api/run-completions/{row['id']}/logs").json()[0]["message"]
        == "Pulled jobs"
    )
    assert client.delete("/api/notifications").json() == {"cleared": 1}
    assert (
        client.get("/api/run-completions", params={"surface": "notifications"}).json()
        == []
    )
    assert len(client.get("/api/run-completions").json()) == 1
    assert client.delete("/api/run-completions").json() == {"cleared": 1}
    assert client.delete("/api/run-completions").json() == {"cleared": 0}
    assert client.get("/api/run-completions").json() == []
    assert client.get(f"/api/run-completions/{row['id']}/logs").status_code == 404
    with Session(app.state.engine) as session:
        # A repeated callback cannot resurrect cleared history.
        for run_id in ("old", "new"):
            record_run_completion(
                session,
                run_id=run_id,
                kind="pull",
                label="Done",
                status="succeeded",
                error=None,
                completed_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            )
    assert [r["runId"] for r in client.get("/api/run-completions").json()] == ["new"]
    assert [
        r["runId"]
        for r in client.get(
            "/api/run-completions", params={"surface": "notifications"}
        ).json()
    ] == ["new"]


def test_terminal_logs_survive_removal_of_transient_run(app_client):
    app, client = app_client

    def work(reporter):
        reporter.begin(2, "Reading sources")
        reporter.step(1, label="Source imported")
        reporter.begin(1, "Building profile")
        return {"ok": True}

    run_id = app.state.run_manager.submit("discover", work)
    for future in list(app.state.run_manager._futures.values()):
        future.result(timeout=2)
    [row] = client.get("/api/run-completions").json()
    # Log reads come from the workspace DB, not the RunManager cache/files.
    from unittest.mock import patch

    with patch.object(app.state.run_manager, "get", return_value=None):
        logs = client.get(f"/api/run-completions/{row['id']}/logs").json()
    assert row["runId"] == run_id
    assert [entry["message"] for entry in logs] == [
        "Reading sources",
        "Source imported",
        "Building profile",
        "Building profile",
    ]
    assert logs[-1]["state"] == "done"


def test_clearing_notifications_preserves_message_identity_and_application(app_client):
    from resume_tailor_harness.tracking.tables import Application, Job, Notification

    app, client = app_client
    with Session(app.state.engine) as session:
        job = Job(
            source="manual",
            company="Example",
            title="Engineer",
            url="https://example.com/job",
        )
        session.add(job)
        session.commit()
        application = Application(job_id=_persisted_id(job.id))
        session.add(application)
        session.commit()
        notification = Notification(
            application_id=_persisted_id(application.id),
            kind="interview",
            proposed_status="interview",
            evidence="Invitation",
            message_id="message-1",
        )
        session.add(notification)
        session.commit()
        notification_id = _persisted_id(notification.id)
        application_id = _persisted_id(application.id)
    assert client.delete("/api/notifications").json() == {"cleared": 1}
    assert client.get("/api/notifications").json() == []
    with Session(app.state.engine) as session:
        stored_notification = session.get(Notification, notification_id)
        stored_application = session.get(Application, application_id)
        assert stored_notification is not None
        assert stored_application is not None
        assert stored_notification.message_id == "message-1"
        assert stored_notification.state == "cleared"
        assert stored_application.status == "ready"


def test_history_and_clear_state_survive_restart(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'workspace.db').as_posix()}"
    config_dir = tmp_path / "config"
    env_path = tmp_path / ".env"
    data_dir = tmp_path / "data"
    first_app = create_app(
        db_url=db_url,
        config_dir=config_dir,
        env_path=env_path,
        data_dir=data_dir,
    )
    with TestClient(first_app) as client:
        with Session(first_app.state.engine) as session:
            record_run_completion(
                session,
                run_id="durable",
                kind="pull",
                label="Completed",
                status="succeeded",
                error=None,
                completed_at=datetime.now(timezone.utc),
                logs=[
                    {
                        "timestamp": "2026-09-09T12:00:00Z",
                        "message": "Saved",
                        "state": "done",
                    }
                ],
            )
    with TestClient(
        create_app(
            db_url=db_url,
            config_dir=config_dir,
            env_path=env_path,
            data_dir=data_dir,
        )
    ) as client:
        [row] = client.get("/api/run-completions").json()
        assert (
            client.get(f"/api/run-completions/{row['id']}/logs").json()[0]["message"]
            == "Saved"
        )
        assert client.delete("/api/run-completions").json() == {"cleared": 1}
        assert (
            len(
                client.get(
                    "/api/run-completions", params={"surface": "notifications"}
                ).json()
            )
            == 1
        )
    with TestClient(
        create_app(
            db_url=db_url,
            config_dir=config_dir,
            env_path=env_path,
            data_dir=data_dir,
        )
    ) as client:
        assert client.get("/api/run-completions").json() == []
        assert (
            len(
                client.get(
                    "/api/run-completions", params={"surface": "notifications"}
                ).json()
            )
            == 1
        )


def test_operation_log_retention_is_bounded(tmp_path):
    from resume_tailor_harness.api.runs.manager import RunProgressReporter
    from resume_tailor_harness.progress import read_progress

    reporter = RunProgressReporter("bounded", "pull", tmp_path)
    reporter.begin(250, "Starting")
    for index in range(250):
        reporter.step(index, label=f"{index}:" + "x" * 3000)
    reporter.done()
    record = read_progress("bounded", tmp_path)
    assert record is not None
    assert len(record["logs"]) == 200
    assert all(len(entry["message"]) <= 2000 for entry in record["logs"])
    assert record["logs"][-1]["state"] == "done"
