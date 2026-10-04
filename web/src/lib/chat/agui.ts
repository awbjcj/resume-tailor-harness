import { EventType } from "@ag-ui/core";
import { EventSchemas } from "@ag-ui/core/schemas";

import { parseStreamEvent, type StreamEvent } from "./events";

/** Validate the protocol envelope and then the application payload. Never move
 * the durable cursor for a malformed event or an unindexed lifecycle frame. */
export function parseAguiEvent(value: unknown): StreamEvent | null {
  const parsed = EventSchemas.safeParse(value);
  if (!parsed.success) return null;
  const event = parsed.data;
  const i = event.rawEvent?.index;
  let t: string;
  let v: unknown;
  try {
    switch (event.type) {
      case EventType.TEXT_MESSAGE_CHUNK:
        t = "text"; v = { text: event.delta }; break;
      case EventType.REASONING_MESSAGE_CHUNK:
        t = "reasoning"; v = { text: event.delta }; break;
      case EventType.TOOL_CALL_CHUNK:
        t = "tool_started";
        v = { ...JSON.parse(event.delta ?? "{}"), callId: event.toolCallId, name: event.toolCallName };
        break;
      case EventType.TOOL_CALL_RESULT:
        if (typeof event.content !== "string") return null;
        t = "tool_completed";
        v = { ...JSON.parse(event.content), callId: event.toolCallId };
        break;
      case EventType.RUN_FINISHED:
        t = "completed"; v = {}; break;
      case EventType.RUN_ERROR:
        t = "failed"; v = { message: event.message, code: event.code ?? "RUN_ERROR" }; break;
      case EventType.CUSTOM:
        if (event.name !== "resume.notice" && event.name !== "resume.settled") return null;
        t = event.name.slice("resume.".length); v = event.value; break;
      default:
        return null;
    }
  } catch { return null; }
  return parseStreamEvent({ i, t, v });
}
