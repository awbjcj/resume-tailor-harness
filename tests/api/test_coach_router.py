import io
import json
import time

from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.routers import coach as coach_router
from resume_tailor_harness.profile.coach_store import (
    CoachDraftNote,
    CoachTopic,
    CoachTurnRecord,
    apply_turn_delta,
    create_session,
    end_session,
)


def _client(tmp_path):
    env = tmp_path / "empty.env"
    env.write_text("", encoding="utf-8")
    return TestClient(
        create_app(
            db_url="sqlite://",
            data_dir=tmp_path / "data",
            config_dir=tmp_path / "config",
            env_path=env,
            api_token="",
        )
    )


def _seed_primary(client):
    response = client.post(
        "/api/profile/sources",
        files={"file": ("resume.txt", io.BytesIO(b"Acme experience"), "text/plain")},
        data={"primary": "true", "mode": "literal"},
    )
    assert response.status_code == 201


def _seed_draft(tmp_path, sid="s1"):
    profile_dir = tmp_path / "data" / "profile"
    create_session(
        profile_dir,
        sid,
        [CoachTopic(id="t1", gap="Acme impact")],
        CoachTurnRecord(role="coach", kind="question", text="First?", topic_id="t1"),
    )
    apply_turn_delta(
        profile_dir,
        sid,
        user_text="I cut deploy time 40%.",
        coach_turn=CoachTurnRecord(
            role="coach", kind="draft_note", text="Draft.", topic_id="t1"
        ),
        new_topics=[],
        skipped_topic_ids=[],
        draft=CoachDraftNote(
            topic_id="t1",
            title="Acme deploys",
            summary="Cut deploy time 40%.",
            quotes=["I cut deploy time 40%."],
        ),
    )


def _wait(client, run_id):
    for _ in range(100):
        run = client.get(f"/api/runs/{run_id}").json()
        if run["state"] in {"done", "error"}:
            return run
        time.sleep(0.02)
    raise AssertionError("run never finished")


def _view(sid="s1", status="active"):
    return {
        "sessionId": sid,
        "startedAt": "2026-07-15T00:00:00+00:00",
        "endedAt": None,
        "status": status,
        "turns": [],
        "topics": [],
        "draftNotes": [],
        "recap": None,
        "impact": None,
    }


def test_start_guards_and_opening_run(monkeypatch, tmp_path):
    client = _client(tmp_path)
    monkeypatch.setattr(
        "resume_tailor_harness.llm_runner.resolve_api_key",
        lambda model, **_kwargs: None,
    )
    with client:
        assert client.post("/api/profile/coach/sessions").status_code == 400
        monkeypatch.setattr(
            "resume_tailor_harness.llm_runner.resolve_api_key",
            lambda model, **_kwargs: "key",
        )
        monkeypatch.setattr(
            coach_router, "run_opening_turn", lambda reporter, **kwargs: _view()
        )
        response = client.post("/api/profile/coach/sessions")
        assert response.status_code == 202
        assert _wait(client, response.json()["runId"])["state"] == "done"


def test_profile_change_approval_endpoint_is_revision_bound_and_scoped(
    tmp_path, monkeypatch
):
    from resume_tailor_harness.profile.conversation import (
        ProfileChange,
        ProfileChangeSet,
        prepare_changes,
    )

    client = _client(tmp_path)
    root = tmp_path / "data" / "profile"
    with client:
        create_session(
            root,
            "s1",
            [CoachTopic(id="t1", gap="Profile")],
            CoachTurnRecord(
                role="coach", kind="question", text="Your name?", topic_id="t1"
            ),
        )
        proposal = ProfileChangeSet(
            title="Create profile",
            changes=[
                ProfileChange(
                    entity="profile",
                    operation="create",
                    values={"contact": {"name": "Ada"}},
                    quotes=["My name is Ada"],
                )
            ],
        )
        draft = prepare_changes(root, proposal, "My name is Ada", source_ref="coach:s1")
        apply_turn_delta(
            root,
            "s1",
            user_text="My name is Ada",
            coach_turn=CoachTurnRecord(
                role="coach", kind="profile_changes", text="Review"
            ),
            new_topics=[],
            skipped_topic_ids=[],
            draft=None,
            change_draft=draft,
        )
        path = f"/api/profile/coach/sessions/s1/changes/{draft.id}"
        assert not (root / "facts.json").exists()
        wrong = client.post(path, json={"decision": "apply", "revision": "0" * 64})
        assert (
            wrong.status_code == 409
            and wrong.json()["error"]["code"] == "PROFILE_STALE"
        )
        assert (
            client.post(
                path.replace("sessions/s1", "sessions/missing"),
                json={"decision": "apply", "revision": draft.revision},
            ).status_code
            == 404
        )
        result = client.post(
            path, json={"decision": "apply", "revision": draft.revision}
        )
        assert result.status_code == 200
        assert result.json()["changeDrafts"][0]["status"] == "applied"
        assert (
            client.post(
                path, json={"decision": "apply", "revision": draft.revision}
            ).status_code
            == 200
        )
        # The public build flow must admit a profile with no resume or model key.
        build = client.post("/api/profile/build")
        assert build.status_code == 202
        assert _wait(client, build.json()["runId"])["state"] == "done"

        monkeypatch.setattr(
            "resume_tailor_harness.llm_runner.resolve_api_key",
            lambda model, **kwargs: "key",
        )

        def recap(reporter, **kwargs):
            end_session(root, "s1", "Profile created.")
            return coach_router.session_view(root, "s1")

        monkeypatch.setattr(coach_router, "run_recap_turn", recap)
        ended = client.post("/api/profile/coach/sessions/s1/end", json={"build": True})
        assert ended.status_code == 202
        result = _wait(client, ended.json()["runId"])
        assert result["state"] == "done" and result["result"]["buildRunId"]
        assert _wait(client, result["result"]["buildRunId"])["state"] == "done"


def test_session_fetch_message_and_unknown_mapping(monkeypatch, tmp_path):
    env = tmp_path / "empty.env"
    env.write_text("", encoding="utf-8")
    app = create_app(
        db_url="sqlite://",
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        env_path=env,
        api_token="",
    )
    client = TestClient(app)
    monkeypatch.setattr(
        "resume_tailor_harness.llm_runner.resolve_api_key",
        lambda model, **_kwargs: "key",
    )
    with client:
        _seed_primary(client)
        _seed_draft(tmp_path)
        assert client.get("/api/profile/coach/sessions/s1").status_code == 200
        assert client.get("/api/profile/coach/sessions/nope").status_code == 404
        monkeypatch.setattr(
            coach_router, "run_message_turn", lambda reporter, **kwargs: _view()
        )
        sent = client.post(
            "/api/profile/coach/sessions/s1/messages", json={"message": "hi"}
        )
        assert sent.status_code == 202
        run_id = sent.json()["runId"]
        assert _wait(client, run_id)["state"] == "done"
        rows = [
            json.loads(line)
            for line in app.state.run_manager.stream_path(run_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert rows[-1]["t"] == "completed"


def test_note_save_discard_and_conflicts(monkeypatch, tmp_path):
    client = _client(tmp_path)
    monkeypatch.setattr(
        "resume_tailor_harness.llm_runner.resolve_api_key",
        lambda model, **_kwargs: "key",
    )
    with client:
        _seed_primary(client)
        _seed_draft(tmp_path)
        body = {
            "title": "Acme deploys",
            "summary": "Cut deploy time 40%.",
            "quotes": ["I cut deploy time 40%."],
        }
        saved = client.post("/api/profile/coach/sessions/s1/notes/t1", json=body)
        assert saved.status_code == 200 and saved.json()["docId"]
        assert (
            client.post(
                "/api/profile/coach/sessions/s1/notes/t1", json=body
            ).status_code
            == 409
        )

        # A separate pending draft exercises DELETE.
        from resume_tailor_harness.profile.coach_store import end_session

        end_session(tmp_path / "data" / "profile", "s1", "done")
        create_session(
            tmp_path / "data" / "profile",
            "s2",
            [CoachTopic(id="t1", gap="g")],
            CoachTurnRecord(role="coach", kind="question", text="q", topic_id="t1"),
        )
        apply_turn_delta(
            tmp_path / "data" / "profile",
            "s2",
            user_text="evidence",
            coach_turn=CoachTurnRecord(
                role="coach", kind="draft_note", text="d", topic_id="t1"
            ),
            new_topics=[],
            skipped_topic_ids=[],
            draft=CoachDraftNote(
                topic_id="t1", title="T", summary="S", quotes=["evidence"]
            ),
        )
        discarded = client.delete("/api/profile/coach/sessions/s2/notes/t1")
        assert discarded.status_code == 200
        assert discarded.json()["draftNotes"][0]["status"] == "discarded"


def test_end_run_returns_nested_build_id(monkeypatch, tmp_path):
    client = _client(tmp_path)
    monkeypatch.setattr(
        "resume_tailor_harness.llm_runner.resolve_api_key",
        lambda model, **_kwargs: "key",
    )
    with client:
        _seed_primary(client)
        _seed_draft(tmp_path)
        body = {
            "title": "Acme",
            "summary": "Cut deploy time 40%.",
            "quotes": ["I cut deploy time 40%."],
        }
        assert (
            client.post(
                "/api/profile/coach/sessions/s1/notes/t1", json=body
            ).status_code
            == 200
        )
        ended_view = _view(status="ended") | {
            "draftNotes": [
                {
                    "topicId": "t1",
                    "title": "T",
                    "summary": "S",
                    "quotes": ["q"],
                    "status": "saved",
                }
            ],
            "recap": "Covered Acme.",
        }
        monkeypatch.setattr(
            coach_router, "run_recap_turn", lambda reporter, **kwargs: ended_view
        )
        monkeypatch.setattr(
            coach_router,
            "run_build_with_impact",
            lambda reporter, **kwargs: {"impact": {}},
        )
        response = client.post(
            "/api/profile/coach/sessions/s1/end", json={"build": True}
        )
        run = _wait(client, response.json()["runId"])
        assert run["state"] == "done"
        assert run["result"]["buildRunId"]


def test_coach_archive_filters_unarchive_and_delete(tmp_path):
    client = _client(tmp_path)
    with client:
        _seed_draft(tmp_path)
        end_session(tmp_path / "data" / "profile", "s1", "recap")

        renamed = client.patch(
            "/api/profile/coach/sessions/s1", json={"title": "Leadership evidence"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["sessionTitle"] == "Leadership evidence"

        archived = client.post("/api/profile/coach/sessions/s1/archive")
        assert archived.status_code == 200
        assert archived.json()["archivedAt"]
        assert client.get("/api/profile/coach/sessions").json()["sessions"] == []
        included = client.get(
            "/api/profile/coach/sessions", params={"includeArchived": "true"}
        ).json()["sessions"]
        assert included[0]["sessionId"] == "s1"
        assert included[0]["sessionTitle"] == "Leadership evidence"

        assert (
            client.post("/api/profile/coach/sessions/s1/unarchive").status_code == 200
        )
        assert (
            client.post("/api/profile/coach/sessions/s1/unarchive").status_code == 409
        )
        assert client.delete("/api/profile/coach/sessions/s1").status_code == 204
        assert client.delete("/api/profile/coach/sessions/s1").status_code == 404


def test_coach_archive_rejects_active_and_invalid_status_filter(tmp_path):
    client = _client(tmp_path)
    with client:
        _seed_draft(tmp_path)

        assert client.post("/api/profile/coach/sessions/s1/archive").status_code == 409
        assert (
            client.get(
                "/api/profile/coach/sessions", params={"status": "paused"}
            ).status_code
            == 422
        )
