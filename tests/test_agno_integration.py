"""Exercise Agno's real agent loop and provider SDK against an offline transport.

These regressions need more than fake runners: GPT-6 must request encrypted
reasoning and replay it beside tool results, and provider cache-write usage
must survive the model parser and run aggregation into our operational trace.
"""

import json
from typing import Annotated, Any

from agno.agent import Agent
import httpx
import pytest

from resume_tailor_harness.agent_trace import agent_trace, read_trace
from resume_tailor_harness.config import Settings
from resume_tailor_harness.llm_runner import (
    AgentRunner,
    build_model,
    retry_kwargs,
    tool_kwargs,
    use_json_mode_for,
)
from resume_tailor_harness.models.resume import ResumeContent
from resume_tailor_harness.sessions.stream import Completed, Failed, ToolCompleted


def _response(model_id: str, output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 0,
        "model": model_id,
        "status": "completed",
        "output": output,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 10},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
    }


def _sse_response(response: dict[str, Any]) -> httpx.Response:
    events = [{"type": "response.created", "response": {**response, "output": []}}]
    for index, item in enumerate(response["output"]):
        events.append(
            {"type": "response.output_item.added", "output_index": index, "item": item}
        )
        if item["type"] == "message":
            events.append(
                {
                    "type": "response.output_text.delta",
                    "output_index": index,
                    "content_index": 0,
                    "item_id": item["id"],
                    "delta": item["content"][0]["text"],
                }
            )
        events.append(
            {"type": "response.output_item.done", "output_index": index, "item": item}
        )
    events.append({"type": "response.completed", "response": response})
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text="".join(
            f"event: {event['type']}\ndata: {json.dumps({**event, 'sequence_number': i})}\n\n"
            for i, event in enumerate(events)
        ),
    )


@pytest.mark.parametrize("mode", ["sync", "async", "stream"])
@pytest.mark.parametrize("model_id", ["openai:gpt-5.6-terra", "openai:gpt-6.1-sol"])
async def test_reasoning_tool_loop_preserves_schema_and_usage(tmp_path, mode, model_id):
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="offline-key",
        openai_base_url="https://provider.invalid/v1",
        openai_route_mode="api",
        llm_retries=0,
    )
    model = build_model(model_id, reasoning=True, settings=settings)
    expected = ResumeContent.model_validate({"contact": {"name": "Test User"}})
    calls = []

    def lookup_profile(fact_id: Annotated[str, "Verified profile fact identifier"]) -> str:
        """Read one verified profile fact without changing the profile."""
        calls.append(fact_id)
        return "Test User" if fact_id == "contact-name" else "Unknown fact"

    reasoning = {
        "type": "reasoning",
        "id": "rs_fixture",
        "summary": [],
        "encrypted_content": "opaque-reasoning-fixture",
    }
    function_call = {
        "type": "function_call",
        "id": "fc_fixture",
        "call_id": "call_fixture",
        "name": "lookup_profile",
        "arguments": '{"fact_id":"contact-name"}',
        "status": "completed",
    }
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert str(request.url) == "https://provider.invalid/v1/responses"
        assert request.headers["authorization"] == "Bearer offline-key"
        assert len(requests) <= 2, "The read-only tool loop must finish after one lookup"
        output = (
            [reasoning, function_call]
            if len(requests) == 1
            else [
                {
                    "type": "message",
                    "id": "msg_fixture",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": expected.model_dump_json(),
                            "annotations": [],
                        }
                    ],
                }
            ]
        )
        response = _response(model.id, output)
        return (
            _sse_response(response)
            if body.get("stream")
            else httpx.Response(200, json=response)
        )

    runner = AgentRunner(
        Agent(
            model=model,
            tools=[lookup_profile],
            output_schema=ResumeContent,
            use_json_mode=use_json_mode_for(model, ResumeContent),
            telemetry=False,
            **retry_kwargs(),
            **tool_kwargs(),
        ),
        settings=settings,
    )
    trace = tmp_path / "agent.ndjson"
    transport = httpx.MockTransport(respond)
    with agent_trace(trace):
        if mode == "async":
            async with httpx.AsyncClient(transport=transport) as client:
                model.http_client = client
                try:
                    result = await runner.arun("Look up the contact name and format it.")
                finally:
                    await runner.aclose()
        else:
            with httpx.Client(transport=transport) as client:
                model.http_client = client
                if mode == "stream":
                    events = list(runner.stream("Look up the contact name and format it."))
                    assert not any(isinstance(event, Failed) for event in events)
                    assert sum(isinstance(event, ToolCompleted) for event in events) == 1
                    assert isinstance(events[-1], Completed)
                    result = events[-1].response
                else:
                    result = runner.run("Look up the contact name and format it.")

    assert result is not None
    assert result.content == expected
    assert calls == ["contact-name"]
    assert len(requests) == 2
    for body in requests:
        assert body["store"] is False
        assert "previous_response_id" not in body
        assert "reasoning.encrypted_content" in body.get("include", [])
        tool = next(t for t in body["tools"] if t.get("name") == "lookup_profile")
        assert tool["parameters"]["properties"]["fact_id"]["type"] == "string"
        assert body["text"]["format"]["name"] == "ResumeContent"

    replay = requests[1]["input"]
    assert reasoning in replay
    assert replay.index(reasoning) < next(
        i for i, item in enumerate(replay) if item.get("type") == "function_call"
    )
    assert any(
        item.get("type") == "function_call_output"
        and item.get("call_id") == "call_fixture"
        and item.get("output") == "Test User"
        for item in replay
    )
    assert result.metrics.input_tokens == 200
    assert result.metrics.cache_read_tokens == 60
    assert result.metrics.cache_write_tokens == 20
    assert result.metrics.reasoning_tokens == 10
    if mode != "stream":
        row = read_trace(trace)[0]
        assert row["cacheWriteTokens"] == 20
        assert row["toolCalls"] == 1
        assert "opaque-reasoning-fixture" not in trace.read_text(encoding="utf-8")
