import json

from ag_ui.core import Event, RunErrorEvent, TextMessageChunkEvent, ToolCallResultEvent
from pydantic import TypeAdapter

from tests.api.test_run_stream_route import InlineExecutor, _rows
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.runs.agui import project_event
from resume_tailor_harness.sessions.stream import (
    Completed,
    RunStreamSink,
    Settled,
    TextDelta,
    ToolCompleted,
    ToolStarted,
)


def test_agui_projection_is_valid_and_preserves_replay_and_settling(tmp_path):
    app = create_app(
        db_url="sqlite://", run_executor=InlineExecutor(), runs_root=tmp_path
    )
    with TestClient(app) as client:
        run_id = app.state.run_manager.create("scout-turn")
        sink = RunStreamSink(app.state.run_manager.stream_path(run_id), flush_chars=1)
        for event in [
            TextDelta("Hello"),
            ToolStarted("call", "research", "query"),
            ToolCompleted("call", "research", "Evidence", True),
            Settled(),
            Completed(),
        ]:
            sink.emit(event)
        sink.close()
        response = client.get(f"/api/runs/{run_id}/stream?protocol=ag-ui&offset=1")
        assert response.status_code == 200
        rows = _rows(response)
    for row in rows:
        TypeAdapter(Event).validate_python(row)
    assert rows[0]["type"] == "RUN_STARTED"
    assert [row["rawEvent"]["index"] for row in rows[1:]] == [1, 2, 3, 4]
    assert rows[1]["toolCallId"] == rows[2]["toolCallId"] == "call"
    assert json.loads(rows[2]["content"])["resultPreview"] == "Evidence"
    assert rows[-2]["type"] == "CUSTOM"
    assert rows[-2]["name"] == "resume.settled"
    assert rows[-1]["type"] == "RUN_FINISHED"


def test_agui_chunks_keep_message_identity_and_errors_remain_terminal():
    first = project_event({"i": 0, "t": "text", "v": {"text": "a"}}, "r", "s")
    second = project_event({"i": 1, "t": "text", "v": {"text": "b"}}, "r", "s")
    assert isinstance(first, TextMessageChunkEvent)
    assert isinstance(second, TextMessageChunkEvent)
    assert first.message_id == second.message_id
    error = project_event(
        {"i": 2, "t": "failed", "v": {"message": "Stopped", "code": "CANCELLED"}},
        "r",
        "s",
    )
    assert isinstance(error, RunErrorEvent)
    assert error.type == "RUN_ERROR"
    assert error.code == "CANCELLED"


def test_tool_result_messages_do_not_overwrite_each_other():
    def result(call_id):
        return project_event(
            {
                "i": 1,
                "t": "tool_completed",
                "v": {
                    "callId": call_id,
                    "name": "search",
                    "resultPreview": "Found",
                    "ok": True,
                },
            },
            "r",
            "s",
        )

    first, second = result("first"), result("second")
    assert isinstance(first, ToolCallResultEvent)
    assert isinstance(second, ToolCallResultEvent)
    assert first.message_id != second.message_id
