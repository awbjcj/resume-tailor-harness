import { describe, expect, it } from "vitest";
import { parseAguiEvent } from "./agui";

describe("AG-UI durable stream adapter", () => {
  it("projects text and retains the native cursor", () => {
    expect(parseAguiEvent({ type: "TEXT_MESSAGE_CHUNK", messageId: "r:text", role: "assistant", delta: "Hello", rawEvent: { index: 4 } })).toEqual({ i: 4, t: "text", v: { text: "Hello" } });
  });
  it("rejects malformed payloads without consuming a cursor", () => {
    expect(parseAguiEvent({ type: "TOOL_CALL_RESULT", messageId: "m", toolCallId: "t", role: "tool", content: "invalid JSON", rawEvent: { index: 0 } })).toBeNull();
    expect(parseAguiEvent({ type: "TEXT_MESSAGE_CHUNK", delta: "hello", rawEvent: { index: -1 } })).toBeNull();
    expect(parseAguiEvent({ type: "RUN_STARTED", runId: "r", threadId: "s" })).toBeNull();
  });
  it("keeps settled distinct from completion", () => {
    expect(parseAguiEvent({ type: "CUSTOM", name: "resume.settled", value: {}, rawEvent: { index: 1 } })?.t).toBe("settled");
    expect(parseAguiEvent({ type: "RUN_FINISHED", runId: "r", threadId: "s", rawEvent: { index: 2 } })?.t).toBe("completed");
  });
});
