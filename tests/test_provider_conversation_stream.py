"""Exercise the actual Agno + SDK + HTTP stream for every supported provider."""

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from agno.agent import Agent

from resume_tailor_harness.config import Settings
from resume_tailor_harness.llm_runner import AgentRunner, build_search_equipped
from resume_tailor_harness.sessions.stream import (
    Completed,
    Failed,
    ReasoningDelta,
    Sources,
    TextDelta,
    ToolCompleted,
    ToolStarted,
)

MODELS = {
    "openai": "openai:gpt-5.6-terra",
    "deepseek": "deepseek:deepseek-v4-pro",
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini:gemini-3.8-flash",
}


def stream_settings(**overrides: Any) -> Settings:
    options: dict[str, Any] = {"_env_file": None, **overrides}
    return Settings(**options)


def sse(events):
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text="".join(
            (f"event: {event['type']}\n" if "type" in event else "")
            + f"data: {json.dumps(event)}\n\n"
            for event in events
        ),
    )


def responses(provider, first=True, terminal="completed"):
    model = MODELS[provider].split(":")[-1]
    response = {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 0,
        "model": model,
        "status": terminal,
        "output": [],
        "usage": {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
    }
    events = [
        {"type": "response.created", "response": {**response, "status": "in_progress"}}
    ]
    if first:
        events.append(
            {
                "type": "response.reasoning_text.delta"
                if provider == "deepseek"
                else "response.reasoning_summary_text.delta",
                "delta": "Checking sources.",
                "item_id": "rs1",
                "output_index": 0,
                "summary_index": 0,
            }
        )
        search = {"type": "web_search_call", "id": "ws1", "status": "in_progress"}
        events.extend(
            [
                {
                    "type": "response.output_item.added",
                    "output_index": 1,
                    "item": search,
                },
                {
                    "type": "response.output_item.done",
                    "output_index": 1,
                    "item": {
                        **search,
                        "status": "completed",
                        "action": {"type": "search", "query": "test"},
                    },
                },
            ]
        )
        call = {
            "type": "function_call",
            "id": "fc1",
            "call_id": "call1",
            "name": "lookup",
            "arguments": "",
            "status": "in_progress",
        }
        events.extend(
            [
                {"type": "response.output_item.added", "output_index": 2, "item": call},
                {
                    "type": "response.function_call_arguments.delta",
                    "output_index": 2,
                    "item_id": "fc1",
                    "delta": '{"key":',
                },
                {
                    "type": "response.function_call_arguments.delta",
                    "output_index": 2,
                    "item_id": "fc1",
                    "delta": '"profile"}',
                },
                {
                    "type": "response.output_item.done",
                    "output_index": 2,
                    "item": {
                        **call,
                        "arguments": '{"key":"profile"}',
                        "status": "completed",
                    },
                },
            ]
        )
    else:
        events.extend(
            [
                {
                    "type": "response.output_text.delta",
                    "delta": "Verified answer.",
                    "item_id": "msg1",
                    "output_index": 0,
                    "content_index": 0,
                },
                {
                    "type": "response.output_text.annotation.added",
                    "item_id": "msg1",
                    "output_index": 0,
                    "content_index": 0,
                    "annotation_index": 0,
                    "annotation": {
                        "type": "url_citation",
                        "url": "https://example.com/source",
                        "title": "Source",
                        "start_index": 0,
                        "end_index": 8,
                    },
                },
            ]
        )
    if terminal == "incomplete":
        response["incomplete_details"] = {"reason": "max_output_tokens"}
    if terminal != "missing":
        events.append({"type": f"response.{terminal}", "response": response})
    return [{**event, "sequence_number": index} for index, event in enumerate(events)]


def anthropic(first=True, terminal="end_turn"):
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 12, "output_tokens": 0},
            },
        }
    ]
    blocks = (
        [
            (
                {"type": "thinking", "thinking": "", "signature": ""},
                [
                    {"type": "thinking_delta", "thinking": "Checking sources."},
                    {"type": "signature_delta", "signature": "opaque"},
                ],
            ),
            (
                {
                    "type": "server_tool_use",
                    "id": "ws1",
                    "name": "web_search",
                    "input": {},
                },
                [{"type": "input_json_delta", "partial_json": '{"query":"test"}'}],
            ),
            (
                {
                    "type": "web_search_tool_result",
                    "tool_use_id": "ws1",
                    "content": [
                        {
                            "type": "web_search_result",
                            "url": "https://example.com/source",
                            "title": "Source",
                            "encrypted_content": "opaque",
                        }
                    ],
                },
                [],
            ),
            (
                {"type": "tool_use", "id": "call1", "name": "lookup", "input": {}},
                [{"type": "input_json_delta", "partial_json": '{"key":"profile"}'}],
            ),
        ]
        if first
        else [
            (
                {"type": "text", "text": ""},
                [{"type": "text_delta", "text": "Verified answer."}],
            )
        ]
    )
    for index, (block, deltas) in enumerate(blocks):
        events.append(
            {"type": "content_block_start", "index": index, "content_block": block}
        )
        events.extend(
            {"type": "content_block_delta", "index": index, "delta": delta}
            for delta in deltas
        )
        events.append({"type": "content_block_stop", "index": index})
    events.append(
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": "tool_use" if first else terminal,
                "stop_sequence": None,
            },
            "usage": {"output_tokens": 7},
        }
    )
    if terminal != "missing":
        events.append({"type": "message_stop"})
    return events


def gemini(first=True, terminal="STOP"):
    parts = (
        [
            {"thought": True, "text": "Checking sources."},
            {
                "toolCall": {
                    "id": "ws1",
                    "toolType": "GOOGLE_SEARCH_WEB",
                    "args": {"query": "test"},
                },
                "thoughtSignature": "c2ln",
            },
            {
                "toolResponse": {
                    "id": "ws1",
                    "toolType": "GOOGLE_SEARCH_WEB",
                    "response": {"result": "found"},
                }
            },
            {
                "functionCall": {
                    "id": "call1",
                    "name": "lookup",
                    "args": {"key": "profile"},
                },
                "thoughtSignature": "c2ln",
            },
        ]
        if first
        else [{"text": "Verified answer."}]
    )
    candidate = {"content": {"role": "model", "parts": parts}, "index": 0}
    if terminal != "missing":
        candidate["finishReason"] = terminal
    if first:
        candidate["groundingMetadata"] = {
            "webSearchQueries": ["test"],
            "groundingChunks": [
                {"web": {"uri": "https://example.com/source", "title": "Source"}}
            ],
        }
    return [
        {
            "candidates": [candidate],
            "usageMetadata": {
                "promptTokenCount": 12,
                "candidatesTokenCount": 7,
                "totalTokenCount": 19,
            },
        }
    ]


@pytest.mark.parametrize("interruptible", [False, True])
def test_gemini_hosted_tools_without_optional_ids_remain_streamable(interruptible):
    def respond(request):
        events = gemini()
        parts = events[0]["candidates"][0]["content"]["parts"]
        parts[:] = [part for part in parts if "functionCall" not in part]
        for part in parts:
            for key in ("toolCall", "toolResponse"):
                if key in part:
                    del part[key]["id"]
        parts.append({"text": "Verified answer."})
        return sse(events)

    settings, model, native = configured("gemini", respond, interruptible=interruptible)
    events = list(
        AgentRunner(
            Agent(model=model, tools=native, telemetry=False, retries=0),
            settings=settings,
        ).stream("p", checkpoint=(lambda: None) if interruptible else None)
    )
    assert isinstance(events[-1], Completed)
    starts = [e for e in events if isinstance(e, ToolStarted)]
    ends = [e for e in events if isinstance(e, ToolCompleted)]
    assert len(starts) == len(ends) == 1
    assert isinstance(starts[0].call_id, str) and starts[0].call_id
    assert starts[0].call_id == ends[0].call_id


def configured(provider, respond, *, interruptible=False):
    settings = stream_settings(
        sub2api_base_url="https://gateway.invalid",
        **{
            f"sub2api_{provider}_key": "offline-key",
            f"{provider}_route_mode": "subscription",
        },
        llm_retries=0,
    )
    model, native = build_search_equipped(
        MODELS[provider], mode="native", reasoning=True, settings=settings
    )
    transport = httpx.MockTransport(respond)
    if provider in {"openai", "deepseek"}:
        model.http_client = (httpx.AsyncClient if interruptible else httpx.Client)(
            transport=transport
        )
    elif provider == "anthropic":
        model.client_params["http_client"] = (
            httpx.AsyncClient if interruptible else httpx.Client
        )(transport=transport)
    else:
        model.client_params["http_options"]["client_args"] = {"transport": transport}
        model.client_params["http_options"]["async_client_args"] = {
            "transport": transport
        }
    return settings, model, native


@pytest.mark.parametrize("provider", MODELS)
@pytest.mark.parametrize("interruptible", [False, True])
def test_native_gateway_stream_search_reasoning_and_function_replay(
    provider, interruptible
):
    import threading

    owner_thread = threading.get_ident()
    requests = []
    looked_up = []

    def lookup(key: str) -> str:
        """Read a verified profile field."""
        assert threading.get_ident() == owner_thread
        looked_up.append(key)
        return "verified"

    def respond(request):
        requests.append(json.loads(request.content))
        assert len(requests) <= 2
        first = len(requests) == 1
        path = request.url.path
        if provider in {"openai", "deepseek"}:
            assert path == "/v1/responses"
            return sse(responses(provider, first))
        if provider == "anthropic":
            assert path == "/v1/messages"
            return sse(anthropic(first))
        assert path == "/v1beta/models/gemini-3.8-flash:streamGenerateContent"
        return sse(gemini(first))

    settings, model, native = configured(provider, respond, interruptible=interruptible)
    runner = AgentRunner(
        Agent(model=model, tools=[*native, lookup], telemetry=False, retries=0),
        settings=settings,
    )
    events = list(
        runner.stream(
            "Research then look up the profile.",
            checkpoint=(lambda: None) if interruptible else None,
        )
    )
    failures = [event for event in events if isinstance(event, Failed)]
    assert not failures, failures
    assert isinstance(events[-1], Completed)
    assert looked_up == ["profile"]
    assert (
        "".join(e.text for e in events if isinstance(e, TextDelta))
        == "Verified answer."
    )
    assert (
        "".join(e.text for e in events if isinstance(e, ReasoningDelta))
        == "Checking sources."
    )
    assert any(isinstance(e, ToolStarted) and e.name == "web_search" for e in events)
    assert any(
        isinstance(e, ToolCompleted) and e.name == "lookup" and e.ok for e in events
    )
    assert any(
        isinstance(e, Sources)
        and e.items == (("https://example.com/source", "Source"),)
        for e in events
    )
    if provider in {"openai", "deepseek"}:
        assert any(
            row.get("type") == "web_search_call" and row["id"] == "ws1"
            for row in requests[1]["input"]
        )
    if provider == "gemini":
        assert any("googleSearch" in tool for tool in requests[0]["tools"])
        assert any("functionDeclarations" in tool for tool in requests[0]["tools"])
        thinking = requests[0]["generationConfig"]["thinkingConfig"]
        assert thinking.get("includeThoughts", thinking.get("include_thoughts")) is True
        assert requests[0]["toolConfig"]["includeServerSideToolInvocations"] is True
        history = requests[1]["contents"]
        replay = next(row["parts"] for row in history if row["role"] == "model")
        assert any(
            "toolCall" in part and part.get("thoughtSignature") == "c2ln"
            for part in replay
        )
        assert any(part.get("functionCall", {}).get("id") == "call1" for part in replay)
        assert any(
            part.get("functionResponse", {}).get("id") == "call1"
            for row in history
            for part in row["parts"]
        )


@pytest.mark.parametrize("provider", MODELS)
@pytest.mark.parametrize("failure", ["truncated", "missing"])
def test_incomplete_provider_stream_never_succeeds(provider, failure, monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "resume_tailor_harness.llm_runner.record_call",
        lambda agent, response: recorded.append(response),
    )

    def respond(request):
        if provider in {"openai", "deepseek"}:
            return sse(
                responses(
                    provider,
                    False,
                    "incomplete" if failure == "truncated" else "missing",
                )
            )
        if provider == "anthropic":
            return sse(
                anthropic(False, "max_tokens" if failure == "truncated" else "missing")
            )
        return sse(gemini(False, "MAX_TOKENS" if failure == "truncated" else "missing"))

    settings, model, tools = configured(provider, respond)
    events = list(
        AgentRunner(
            Agent(model=model, tools=tools, telemetry=False, retries=0),
            settings=settings,
        ).stream("p")
    )
    assert isinstance(events[-1], Failed)
    assert not any(isinstance(event, Completed) for event in events)
    if failure == "truncated":
        assert len(recorded) == 1
        assert recorded[0].metrics.input_tokens == 12
        assert recorded[0].metrics.output_tokens == 7
    else:
        # These SDK fixtures expose metrics only with the terminal marker.
        assert recorded == []


def test_silent_provider_is_cancelled_and_closed_before_first_token():
    import asyncio
    import time

    closed = []

    class Silent:
        model = None

        async def arun(self, *args, **kwargs):
            try:
                await asyncio.sleep(60)
                yield SimpleNamespace(content="too late")
            finally:
                closed.append(True)

    started = time.monotonic()

    def checkpoint():
        if time.monotonic() - started > 0.1:
            raise RuntimeError("cancelled by user")

    settings = stream_settings(llm_retries=0, llm_retry_delay=0)
    events = list(
        AgentRunner(Silent(), settings=settings).stream("p", checkpoint=checkpoint)
    )
    assert time.monotonic() - started < 2
    assert closed == [True]
    assert events == [Failed("cancelled by user", "RuntimeError")]


def test_run_cancellation_during_silent_io_emits_one_cancelled_terminal(
    tmp_path, monkeypatch
):
    import asyncio
    import time

    from resume_tailor_harness.api.runs.conversation import with_conversation_stream
    from resume_tailor_harness.api.runs.manager import RunCancelled, RunManager
    from resume_tailor_harness.sessions.turns import persona_output

    monkeypatch.setattr(
        "resume_tailor_harness.sessions.turns.get_settings",
        lambda: SimpleNamespace(stream_enabled=True),
    )
    closed = []

    class Silent:
        model = None

        async def arun(self, *args, **kwargs):
            try:
                await asyncio.sleep(60)
                yield SimpleNamespace(content="too late")
            finally:
                closed.append(True)

    started = time.monotonic()

    def checkpoint():
        if time.monotonic() - started > 0.1:
            raise RunCancelled

    path = tmp_path / "stream.ndjson"
    manager = RunManager(root=tmp_path / "runs")
    monkeypatch.setattr(manager, "stream_path", lambda _: path)
    reporter = SimpleNamespace(run_id="cancel", checkpoint=checkpoint)
    runner = AgentRunner(
        Silent(), settings=stream_settings(llm_retries=0, llm_retry_delay=0)
    )
    work = with_conversation_stream(
        manager,
        lambda report, sink: persona_output(runner, "p", sink, report, source="test"),
    )
    with pytest.raises(RunCancelled):
        work(reporter)
    manager.shutdown()
    assert closed == [True]
    rows = [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines()]
    assert [(row["t"], row["v"].get("code")) for row in rows] == [
        ("failed", "CANCELLED")
    ]


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_interleaved_responses_function_arguments_keep_call_identity(provider):
    from agno.models.message import Message
    from resume_tailor_harness.llm_runner import build_model

    settings = stream_settings(
        **{f"{provider}_route_mode": "api", f"{provider}_api_key": "offline-key"},
    )
    model = build_model(MODELS[provider], settings=settings)
    message = Message(role="assistant")
    state = {}

    def parse(event):
        nonlocal state
        parsed, state = model._parse_provider_response_delta(
            SimpleNamespace(**event), message, state
        )
        return parsed

    for ident in ["a", "b"]:
        parse(
            {
                "type": "response.output_item.added",
                "item": SimpleNamespace(
                    type="function_call",
                    id=ident,
                    call_id=f"call-{ident}",
                    name="lookup",
                    arguments="",
                ),
            }
        )
    for ident, delta in [("a", '{"key":'), ("b", '{"key":"B"}'), ("a", '"A"}')]:
        parse(
            {
                "type": "response.function_call_arguments.delta",
                "item_id": ident,
                "delta": delta,
            }
        )
    # A hosted tool completion must not consume either pending function.
    parse(
        {
            "type": "response.output_item.done",
            "item": {"type": "web_search_call", "id": "search", "status": "completed"},
        }
    )
    for ident in ["b", "a"]:
        parsed = parse(
            {
                "type": "response.output_item.done",
                "item": SimpleNamespace(type="function_call", id=ident),
            }
        )
        assert parsed.tool_calls[0]["call_id"] == f"call-{ident}"
        assert json.loads(parsed.tool_calls[0]["function"]["arguments"]) == {
            "key": ident.upper()
        }


@pytest.mark.parametrize("status, expected_calls", [(503, 2), (401, 1)])
def test_agno_error_events_preserve_pre_output_retry_policy(status, expected_calls):
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                status,
                json={
                    "error": {"message": "provider unavailable", "type": "test_error"}
                },
            )
        return sse(responses("openai", False))

    settings, model, tools = configured("openai", respond)
    model.max_retries = 0  # Separate SDK retries from our application policy.
    settings.llm_retries = 1
    settings.llm_retry_delay = 0
    events = list(
        AgentRunner(
            Agent(model=model, tools=tools, retries=0, telemetry=False),
            settings=settings,
        ).stream("p")
    )
    assert len(calls) == expected_calls
    assert isinstance(events[-1], Completed if status == 503 else Failed)


@pytest.mark.parametrize(
    "code, visible, expected_calls",
    [
        ("server_error", False, 2),
        ("invalid_prompt", False, 1),
        ("server_error", True, 1),
    ],
)
def test_responses_failure_events_retry_only_transient_pre_output_errors(
    code, visible, expected_calls
):
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) > 1:
            return sse(responses("openai", False))
        events = responses("openai", False, "failed")
        if not visible:
            events = [events[0], events[-1]]
        events[-1]["response"]["error"] = {"code": code, "message": "Fixture failure"}
        return sse(events)

    settings, model, tools = configured("openai", respond)
    settings.llm_retries = 1
    settings.llm_retry_delay = 0
    events = list(
        AgentRunner(
            Agent(model=model, tools=tools, retries=0, telemetry=False),
            settings=settings,
        ).stream("p")
    )
    assert len(calls) == expected_calls
    assert isinstance(events[-1], Completed if expected_calls == 2 else Failed)
