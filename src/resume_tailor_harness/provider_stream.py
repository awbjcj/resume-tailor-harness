"""Preserve provider stream facts that Agno does not expose consistently.

State belongs to one HTTP request, never to a shared model or tenant. The small
provider_data envelope survives Agno's model-to-run projection; it contains
only bounded tool previews and failure metadata, never opaque reasoning data.
"""

from __future__ import annotations

from contextvars import ContextVar
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from resume_tailor_harness.sessions.stream import Failed, ToolCompleted, ToolStarted

STREAM_KEY = "resume_stream"


def value(obj: Any, key: str, default: Any = None) -> Any:
    return (
        obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    )


def preview(data: Any, limit: int = 160) -> str:
    text = " ".join((data if isinstance(data, str) else repr(data)).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def attach(parsed: Any, *events: ToolStarted | ToolCompleted | Failed) -> Any:
    state = _request.get()
    filtered = []
    for event in events:
        if isinstance(event, ToolStarted) and state is not None:
            snapshot = (event.name, event.args_preview)
            if state.previews.get(event.call_id) == snapshot:
                continue
            state.previews[event.call_id] = snapshot
        filtered.append(event)
    events = tuple(filtered)
    if events:
        parsed.provider_data = dict(parsed.provider_data or {})
        # A dict (not a list) avoids Agno accumulating every preview into history.
        previous = parsed.provider_data.get(STREAM_KEY, {}).get("events", [])
        parsed.provider_data[STREAM_KEY] = {
            "events": [
                *previous,
                *[{"t": event.tag, "v": event.payload()} for event in events],
            ]
        }
    return parsed


@dataclass
class RequestState:
    terminal: bool = False
    failure: Failed | None = None
    blocks: dict[int, tuple[str, str, str]] = field(default_factory=dict)
    search_id: str = field(default_factory=lambda: f"search-{uuid4().hex}")
    searched: bool = False
    previews: dict[str, tuple[str, str]] = field(default_factory=dict)
    anonymous_tools: dict[str, list[str]] = field(default_factory=dict)


_request: ContextVar[RequestState | None] = ContextVar("provider_stream", default=None)


class StreamCapture(list[Exception]):
    """Retain reported usage even if failure prevents Agno's final RunOutput."""

    metrics: Any = None

    def collect(self, chunk):
        usage = chunk.response_usage
        if usage is not None:
            self.metrics = (
                deepcopy(usage) if self.metrics is None else self.metrics + usage
            )


_errors: ContextVar[StreamCapture | None] = ContextVar("provider_errors", default=None)


@contextmanager
def capture_errors():
    errors = StreamCapture()
    token = _errors.set(errors)
    try:
        yield errors
    finally:
        _errors.reset(token)


class StreamLifecycle:
    """Detect a clean HTTP EOF that lacks the provider's completion marker."""

    async def arun_function_call(self, function_call):
        from inspect import isasyncgenfunction, iscoroutine, iscoroutinefunction

        from agno.exceptions import AgentRunException
        from agno.tools.function import FunctionExecutionResult
        from agno.utils.timer import Timer

        from resume_tailor_harness.stream_execution import worker_tools

        function = function_call.function
        entrypoint = function.entrypoint
        if (
            not worker_tools.get()
            or iscoroutinefunction(entrypoint)
            or isasyncgenfunction(entrypoint)
            or iscoroutine(entrypoint)
            or any(iscoroutinefunction(hook) for hook in function.tool_hooks or [])
        ):
            return await super().arun_function_call(function_call)

        # Conversation tools close over run-thread Sessions and mutable budgets.
        # Agno normally uses to_thread + gather here, which violates that custody.
        timer = Timer()
        timer.start()
        try:
            result = function_call.execute()
            success = result.status == "success"
        except AgentRunException as exc:
            success = exc
            result = FunctionExecutionResult(status="failure")
        finally:
            timer.stop()
        return success, timer, function_call, result

    def invoke_stream(self, *args, **kwargs):
        from agno.models.response import ModelResponse

        state = RequestState()
        token = _request.set(state)
        stream = super().invoke_stream(*args, **kwargs)
        try:
            for chunk in stream:
                capture = _errors.get()
                if capture is not None:
                    capture.collect(chunk)
                yield chunk
            if not state.terminal:
                yield attach(
                    ModelResponse(),
                    Failed(
                        "The provider connection ended before the response completed.",
                        "INCOMPLETE_STREAM",
                    ),
                )
        except Exception as exc:
            errors = _errors.get()
            if errors is not None:
                errors.append(exc)
            raise
        finally:
            try:
                stream.close()
            finally:
                _request.reset(token)

    async def ainvoke_stream(self, *args, **kwargs):
        from agno.models.response import ModelResponse

        state = RequestState()
        token = _request.set(state)
        stream = super().ainvoke_stream(*args, **kwargs)
        try:
            async for chunk in stream:
                capture = _errors.get()
                if capture is not None:
                    capture.collect(chunk)
                yield chunk
            if not state.terminal:
                yield attach(
                    ModelResponse(),
                    Failed(
                        "The provider connection ended before the response completed.",
                        "INCOMPLETE_STREAM",
                    ),
                )
        except Exception as exc:
            errors = _errors.get()
            if errors is not None:
                errors.append(exc)
            raise
        finally:
            try:
                await stream.aclose()
            finally:
                _request.reset(token)


def responses_delta(model, event, message, calls, parse):
    """Keep concurrent function arguments isolated; expose hosted search events."""
    from agno.models.response import ModelResponse

    kind = value(event, "type")
    item = value(event, "item")
    item_type = value(item, "type")
    state = _request.get()
    if kind in {
        "response.completed",
        "response.incomplete",
        "response.failed",
        "error",
    }:
        if state is not None:
            state.terminal = True
    if kind in {"response.failed", "response.incomplete", "error"}:
        response = value(event, "response")
        error = value(response, "error") or event
        reason = value(value(response, "incomplete_details"), "reason")
        parsed = ModelResponse()
        usage = value(response, "usage")
        if usage is not None:
            parsed.response_usage = model._get_metrics(usage)
        return attach(
            parsed,
            Failed(
                str(
                    value(error, "message")
                    or reason
                    or "The provider could not complete the response."
                ),
                "INCOMPLETE_RESPONSE"
                if kind == "response.incomplete"
                else str(value(error, "code") or "PROVIDER_ERROR"),
            ),
        ), calls
    if kind == "response.output_item.added" and item_type == "function_call":
        identity = value(item, "id") or value(item, "call_id")
        call = {
            "id": identity,
            "call_id": value(item, "call_id") or identity,
            "type": "function",
            "function": {
                "name": value(item, "name"),
                "arguments": value(item, "arguments") or "",
            },
        }
        calls[identity] = call
        return attach(
            ModelResponse(),
            ToolStarted(
                call["call_id"],
                call["function"]["name"],
                preview(call["function"]["arguments"]),
            ),
        ), calls
    if kind == "response.function_call_arguments.delta":
        call = calls.get(value(event, "item_id"))
        if call is None:
            return attach(
                ModelResponse(),
                Failed(
                    "Tool arguments arrived without a tool call.", "INVALID_TOOL_STREAM"
                ),
            ), calls
        call["function"]["arguments"] += value(event, "delta", "")
        return attach(
            ModelResponse(),
            ToolStarted(
                call["call_id"],
                call["function"]["name"],
                preview(call["function"]["arguments"]),
            ),
        ), calls
    if kind == "response.output_item.done" and item_type == "function_call":
        identity = value(item, "id") or value(item, "call_id")
        call = calls.pop(identity, None)
        if call is None:
            return attach(
                ModelResponse(),
                Failed(
                    "A tool call ended without its start event.", "INVALID_TOOL_STREAM"
                ),
            ), calls
        arguments = value(item, "arguments")
        if isinstance(arguments, str):
            call["function"]["arguments"] = arguments
        if message.tool_calls is None:
            message.tool_calls = []
        message.tool_calls.append(call)
        return ModelResponse(
            tool_calls=[call], extra={"tool_call_ids": [call["call_id"]]}
        ), calls
    # Do not let an unrelated output_item.done flush a pending function call.
    parsed, _ = parse(event, message, {})
    if kind == "response.output_item.added" and item_type == "web_search_call":
        attach(parsed, ToolStarted(value(item, "id"), "web_search"))
    elif kind == "response.output_item.done" and item_type == "web_search_call":
        parsed.provider_data = dict(parsed.provider_data or {})
        parsed.provider_data["native_search_items"] = [
            item if isinstance(item, dict) else item.model_dump(exclude_none=True)
        ]
        action = value(item, "action")
        ok = value(item, "status") not in {"failed", "incomplete"}
        attach(
            parsed,
            ToolCompleted(
                value(item, "id"),
                "web_search",
                preview(value(action, "query") or value(item, "status") or ""),
                ok,
            ),
        )
    return parsed, calls


def anthropic_delta(event, parsed):
    state = _request.get()
    kind = value(event, "type")
    if state is not None and kind == "message_stop":
        state.terminal = True
        if state.failure is not None:
            attach(parsed, state.failure)
    reason = value(value(event, "delta"), "stop_reason")
    if kind == "message_delta" and reason in {"max_tokens", "refusal", "pause_turn"}:
        failure = Failed(
            f"The provider stopped the response: {reason}.", "INCOMPLETE_RESPONSE"
        )
        if state is not None:
            # The next message_stop carries the SDK's accumulated usage.
            state.failure = failure
        else:
            attach(parsed, failure)
    block = value(event, "content_block")
    block_type = value(block, "type")
    if kind == "content_block_start" and block_type in {"tool_use", "server_tool_use"}:
        call_id, name = value(block, "id"), value(block, "name")
        if state is not None:
            state.blocks[value(event, "index")] = (call_id, name, "")
        attach(parsed, ToolStarted(call_id, name))
    elif (
        kind == "content_block_delta"
        and value(value(event, "delta"), "type") == "input_json_delta"
        and state is not None
    ):
        index = value(event, "index")
        if index in state.blocks:
            call_id, name, args = state.blocks[index]
            # Only the preview lives here; the SDK owns the complete JSON.
            args = (args + value(value(event, "delta"), "partial_json", ""))[:160]
            state.blocks[index] = (call_id, name, args)
            attach(parsed, ToolStarted(call_id, name, preview(args)))
    elif kind == "content_block_stop" and block_type in {
        "web_search_tool_result",
        "web_fetch_tool_result",
    }:
        content = value(block, "content")
        error = value(content, "error_code")
        name = "web_search" if block_type == "web_search_tool_result" else "web_fetch"
        attach(
            parsed,
            ToolCompleted(
                value(block, "tool_use_id"),
                name,
                str(error or "Search completed"),
                not bool(error),
            ),
        )
        if isinstance(content, list):
            from agno.models.message import Citations, UrlCitation

            parsed.citations = Citations(
                urls=[
                    UrlCitation(url=value(row, "url"), title=value(row, "title"))
                    for row in content
                    if value(row, "url")
                ]
            )
    return parsed


def gemini_delta(event, parsed):
    state = _request.get()
    for candidate in value(event, "candidates") or []:
        for part in value(value(candidate, "content"), "parts", []) or []:
            tool = value(part, "tool_call")
            result = value(part, "tool_response")
            if tool is not None:
                tool_type = value(tool, "tool_type")
                name = str(value(tool_type, "value", tool_type) or "tool").lower()
                name = (
                    "web_search"
                    if name in {"google_search", "google_search_web"}
                    else name
                )
                if state is not None and name == "web_search":
                    state.searched = True
                call_id = value(tool, "id") or f"hosted-{uuid4().hex}"
                if not value(tool, "id") and state is not None:
                    state.anonymous_tools.setdefault(name, []).append(call_id)
                attach(
                    parsed,
                    ToolStarted(
                        call_id, name, preview(value(tool, "args") or "")
                    ),
                )
            if result is not None:
                tool_type = value(result, "tool_type")
                name = str(value(tool_type, "value", tool_type) or "tool").lower()
                name = (
                    "web_search"
                    if name in {"google_search", "google_search_web"}
                    else name
                )
                call_id = value(result, "id")
                if not call_id:
                    pending = state.anonymous_tools.get(name, []) if state else []
                    call_id = pending.pop(0) if pending else f"hosted-{uuid4().hex}"
                attach(
                    parsed,
                    ToolCompleted(
                        call_id,
                        name,
                        preview(value(result, "response") or ""),
                    ),
                )
        reason = value(candidate, "finish_reason")
        reason = value(reason, "value", reason)
        if reason:
            if state is not None:
                state.terminal = True
            if reason != "STOP":
                attach(
                    parsed,
                    Failed(
                        f"The provider stopped the response: {reason}.",
                        "INCOMPLETE_RESPONSE",
                    ),
                )
                return parsed
        grounding = value(candidate, "grounding_metadata")
        queries = value(grounding, "web_search_queries") or []
        if queries and state is not None and not state.searched:
            state.searched = True
            attach(
                parsed,
                ToolStarted(state.search_id, "web_search", preview(", ".join(queries))),
                ToolCompleted(state.search_id, "web_search", "Search completed"),
            )
    feedback = value(event, "prompt_feedback")
    blocked = value(feedback, "block_reason")
    if blocked:
        if state is not None:
            state.terminal = True
        attach(
            parsed,
            Failed(
                f"The provider blocked the request: {value(blocked, 'value', blocked)}.",
                "PROVIDER_BLOCKED",
            ),
        )
    return parsed
