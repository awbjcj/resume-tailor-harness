from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.services.run_completions import record_run_completion
from resume_tailor_harness.services.run_visibility import CHAT_RUN_KINDS


def _persisted_id(value: int | None) -> int:
    assert value is not None
    return value


def test_run_visibility_contract():
    """New chat operation kinds must be classified on both live and durable paths."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    browser = (root / "web/src/lib/runs/visibility.ts").read_text(encoding="utf-8")
    kind_pattern = r'"((?:career-lab|profile-coach|mock-interview|scout)-[a-z-]+)"'
    assert set(re.findall(kind_pattern, browser)) == CHAT_RUN_KINDS
    routers = root / "src/resume_tailor_harness/api/routers"
    launched = set()
    for name in ("career_lab", "coach", "interview", "scout"):
        launched.update(
            re.findall(
                kind_pattern, (routers / f"{name}.py").read_text(encoding="utf-8")
            )
        )
    assert launched == CHAT_RUN_KINDS


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


def test_scheduled_completion_is_history_but_not_an_unread_flag(app_client):
    app, client = app_client
    run_id = app.state.run_manager.submit(
        "gmailSync",
        lambda _reporter: (_ for _ in ()).throw(RuntimeError("token expired")),
        meta={"scheduled": True},
    )
    for future in list(app.state.run_manager._futures.values()):
        future.result(timeout=2)

    [row] = client.get("/api/run-completions").json()
    assert row["runId"] == run_id
    assert row["status"] == "failed"
    assert row["readAt"] is not None
    assert client.get("/api/run-completions", params={"unread_only": True}).json() == []


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
    assert row["completedAt"].endswith("Z")
    assert [entry["message"] for entry in logs] == [
        "Reading sources",
        "Source imported",
        "Building profile",
        "Building profile",
    ]
    assert all(entry["timestamp"].endswith("Z") for entry in logs)
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


@pytest.mark.parametrize("surface", ["operations", "notifications"])
def test_chat_history_only_surfaces_failures_including_legacy_rows(app_client, surface):
    app, client = app_client
    quiet_ids = []
    failed_ids = set()
    with Session(app.state.engine) as session:
        for kind in sorted(CHAT_RUN_KINDS):
            for status in ("failed", "succeeded", "cancelled"):
                run_id = f"{kind}-{status}"
                row = record_run_completion(
                    session,
                    run_id=run_id,
                    kind=kind,
                    label=kind,
                    status=status,
                    error="boom" if status == "failed" else None,
                    # Quiet rows are newer: filtering must precede the limit.
                    completed_at=datetime(
                        2026, 8, 29 if status == "failed" else 30, tzinfo=timezone.utc
                    ),
                    logs=[{"message": status}],
                )
                if status == "failed":
                    failed_ids.add(run_id)
                    assert row.read_at is None
                else:
                    assert row.read_at is not None
                    quiet_ids.append(row.id)
                    # Simulate pre-policy records, which were unread.
                    row.read_at = None
                    session.add(row)
                    session.commit()

    for unread_only in (True, False):
        rows = client.get(
            "/api/run-completions",
            params={
                "surface": surface,
                "unread_only": unread_only,
                "limit": 100,
            },
        ).json()
        assert {row["runId"] for row in rows} == failed_ids
        [limited] = client.get(
            "/api/run-completions", params={"surface": surface, "limit": 1}
        ).json()
        assert limited["status"] == "failed"
    for completion_id in quiet_ids:
        assert (
            client.get(f"/api/run-completions/{completion_id}/logs").status_code == 404
        )
    assert client.get(f"/api/run-completions/{rows[0]['id']}/logs").json() == [
        {"message": "failed"}
    ]
    assert client.post("/api/run-completions/read-all").json() == {
        "markedRead": len(CHAT_RUN_KINDS)
    }


def test_quiet_chat_still_completes_and_persists(app_client):
    from sqlmodel import select
    from resume_tailor_harness.tracking.tables import RunCompletion, RunOperationLog

    app, client = app_client
    run_id = app.state.run_manager.submit(
        "career-lab-turn", lambda _reporter: {"sessionId": "s1"}
    )
    for future in list(app.state.run_manager._futures.values()):
        future.result(timeout=2)
    assert client.get(f"/api/runs/{run_id}").json()["state"] == "done"
    assert client.get("/api/run-completions").json() == []
    assert client.delete("/api/run-completions").json() == {"cleared": 0}
    with Session(app.state.engine) as session:
        [row] = session.exec(select(RunCompletion)).all()
        assert row.run_id == run_id
        assert session.get(RunOperationLog, run_id) is not None
