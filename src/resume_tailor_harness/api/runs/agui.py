"""AG-UI projection of durable conversation events, without a second run store.

Each source row maps to one chunk/result/custom event. rawEvent.index is the
application replay cursor, not an AG-UI message id. Launch and cancellation stay
on the existing authenticated run endpoints; this endpoint only observes work.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from ag_ui.core import (
    CustomEvent,
    ReasoningMessageChunkEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageChunkEvent,
    ToolCallChunkEvent,
    ToolCallResultEvent,
)

from .stream_sse import stream_events


def project_event(row: dict, run_id: str, thread_id: str):
    index, tag, value = row["i"], row["t"], row["v"]
    cursor = {"index": index}
    # Distinct chunks can be interleaved with tool and reasoning output.
    message_id = f"{run_id}:{tag}"
    if tag == "text":
        return TextMessageChunkEvent(
            message_id=message_id,
            role="assistant",
            delta=value["text"],
            raw_event=cursor,
        )
    if tag == "reasoning":
        return ReasoningMessageChunkEvent(
            message_id=message_id, delta=value["text"], raw_event=cursor
        )
    if tag == "tool_started":
        return ToolCallChunkEvent(
            tool_call_id=value["callId"],
            tool_call_name=value["name"],
            delta=json.dumps({"argsPreview": value["argsPreview"]}),
            raw_event=cursor,
        )
    if tag == "tool_completed":
        return ToolCallResultEvent(
            message_id=f"{run_id}:result:{value['callId']}",
            tool_call_id=value["callId"],
            content=json.dumps(value),
            role="tool",
            raw_event=cursor,
        )
    if tag == "completed":
        return RunFinishedEvent(thread_id=thread_id, run_id=run_id, raw_event=cursor)
    if tag == "failed":
        return RunErrorEvent(
            message=value["message"], code=value["code"], raw_event=cursor
        )
    if tag in {"notice", "settled"}:
        return CustomEvent(name=f"resume.{tag}", value=value, raw_event=cursor)
    raise ValueError(f"Unsupported conversation event: {tag}")


async def agui_stream(
    mgr, run_id: str, thread_id: str, offset: int = 0
) -> AsyncIterator[dict]:
    # Every subscription has valid run boundaries, including resumed streams.
    start = RunStartedEvent(thread_id=thread_id, run_id=run_id)
    yield {"data": start.model_dump_json(by_alias=True, exclude_none=True)}
    async for frame in stream_events(mgr, run_id, offset):
        event = project_event(json.loads(frame["data"]), run_id, thread_id)
        yield {"data": event.model_dump_json(by_alias=True, exclude_none=True)}
