import { describe, expect, it } from "vitest";

import { parseStreamEvent, reduceEvent, type ChatPart } from "./events";

describe("chat stream events", () => {
  it("coalesces text while preserving tool order", () => {
    let parts: ChatPart[] = [];
    parts = reduceEvent(parts, { i: 0, t: "text", v: { text: "a" } });
    parts = reduceEvent(parts, { i: 1, t: "text", v: { text: "b" } });
    parts = reduceEvent(parts, {
      i: 2,
      t: "tool_started",
      v: { callId: "c1", name: "search", argsPreview: "query" },
    });
    parts = reduceEvent(parts, { i: 3, t: "text", v: { text: "c" } });
    expect(parts.map((part) => part.kind)).toEqual(["text", "tool", "text"]);
    expect(parts[0]).toEqual({ kind: "text", text: "ab" });
  });

  it("completes the matching tool call id, not another call of the same name", () => {
    let parts: ChatPart[] = [];
    for (const callId of ["c1", "c2"]) {
      parts = reduceEvent(parts, {
        i: parts.length,
        t: "tool_started",
        v: { callId, name: "search", argsPreview: callId },
      });
    }
    parts = reduceEvent(parts, {
      i: 2,
      t: "tool_completed",
      v: { callId: "c1", name: "search", resultPreview: "done", ok: true },
    });
    expect(parts[0]).toMatchObject({ callId: "c1", done: true });
    expect(parts[1]).toMatchObject({ callId: "c2", done: false });
  });

  it("rejects malformed browser input", () => {
    expect(parseStreamEvent({ i: "0", t: "text", v: { text: "x" } })).toBeNull();
    expect(parseStreamEvent({ i: 0, t: "text", v: { text: 1 } })).toBeNull();
    expect(parseStreamEvent({ i: 0, t: "future", v: {} })).toBeNull();
    expect(parseStreamEvent({ i: 0, t: "completed", v: {} })).not.toBeNull();
  });

  it("updates argument previews without adding duplicate tool cards", () => {
    let parts: ChatPart[] = [];
    for (const argsPreview of ["", '{"query":', '{"query":"jobs"}']) {
      parts = reduceEvent(parts, { i: 0, t: "tool_started", v: { callId: "s1", name: "web_search", argsPreview } });
    }
    expect(parts).toHaveLength(1);
    expect(parts[0]).toMatchObject({ argsPreview: '{"query":"jobs"}', done: false });
    parts = reduceEvent(parts, { i: 1, t: "failed", v: { code: "CANCELLED", message: "Stopped" } });
    expect(parts[0]).toMatchObject({ done: true, ok: false, resultPreview: "Stopped" });
  });

  it("shows hosted tool results even when the provider omits a start", () => {
    const event = { i: 0, t: "tool_completed" as const, v: { callId: "s1", name: "web_search", resultPreview: "Found", ok: true } };
    const parts = reduceEvent([], event);
    expect(parts).toHaveLength(1);
    expect(parts[0]).toMatchObject({ kind: "tool", done: true, ok: true });
    expect(reduceEvent(parts, event)).toBe(parts);
  });

  it("validates source URLs and deduplicates them across deltas", () => {
    for (const url of ["javascript:alert(1)", "https://user:secret@example.com", "not a url"]) {
      expect(parseStreamEvent({ i: 0, t: "sources", v: { items: [{ url, title: "Bad" }] } })).toBeNull();
    }
    const event = { i: 0, t: "sources" as const, v: { items: [{ url: "https://example.com", title: "Source" }] } };
    expect(parseStreamEvent(event)).toEqual(event);
    const parts = reduceEvent([], event);
    expect(reduceEvent(parts, event)).toBe(parts);
    const updated = reduceEvent(parts, { ...event, v: { items: [{ ...event.v.items[0], title: "Updated" }] } });
    expect(updated).toEqual([{ kind: "sources", items: [{ url: "https://example.com", title: "Updated" }] }]);
  });
});
