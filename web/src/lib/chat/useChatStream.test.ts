import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createElement, StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useChatStream } from "./useChatStream";

class FakeEventSource {
  static last: FakeEventSource | null = null;
  static instances: FakeEventSource[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.last = this;
    FakeEventSource.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  send(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

vi.stubGlobal("EventSource", FakeEventSource);
vi.mock("@/features/runs/use-launch-run", () => ({ cancelRun: vi.fn() }));

describe("useChatStream", () => {
  beforeEach(() => {
    FakeEventSource.last = null;
    FakeEventSource.instances = [];
    resetSseLinkTokenCache();
    localStorage.setItem("resume-tailor-harness-token", "token");
  });

  it("accumulates valid events and ignores malformed rows without advancing", async () => {
    const { result } = renderHook(() => useChatStream("run-1"));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    act(() => FakeEventSource.last!.send({ i: "4", t: "text", v: { text: "bad" } }));
    act(() => FakeEventSource.last!.send({ i: 4, t: "text", v: { text: "gap" } }));
    act(() => FakeEventSource.last!.send({ i: 0, t: "text", v: { text: "hi" } }));
    await waitFor(() => expect(result.current.parts).toHaveLength(1));
    act(() => FakeEventSource.last!.onerror?.());
    await waitFor(() => expect(FakeEventSource.last!.url).toContain("offset=1"));
  });

  it("resets all state when run id changes", async () => {
    const { result, rerender } = renderHook(({ id }) => useChatStream(id), {
      initialProps: { id: "run-1" as string | null },
    });
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    act(() => FakeEventSource.last!.send({ i: 0, t: "text", v: { text: "old" } }));
    await waitFor(() => expect(result.current.parts).toHaveLength(1));
    rerender({ id: "run-2" });
    await waitFor(() => expect(result.current.parts).toEqual([]));
    expect(FakeEventSource.last!.url).toContain("run-2");
    expect(FakeEventSource.last!.url).toContain("offset=0");
  });

  it("discards partial output when stopped", async () => {
    const { result } = renderHook(() => useChatStream("run-1"));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    act(() => FakeEventSource.last!.send({ i: 0, t: "text", v: { text: "partial" } }));
    await waitFor(() => expect(result.current.parts).toHaveLength(1));
    act(() => result.current.stop());
    expect(result.current.parts).toEqual([]);
    expect(result.current.status).toBe("idle");
  });

  it("marks visible prose settled without closing the stream", async () => {
    const { result } = renderHook(() => useChatStream("run-1"));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    act(() => FakeEventSource.last!.send({ i: 0, t: "text", v: { text: "done" } }));
    act(() => FakeEventSource.last!.send({ i: 1, t: "settled", v: {} }));
    expect(result.current.status).toBe("settled");
    expect(FakeEventSource.last!.closed).toBe(false);
  });

  it("preserves settled status and the replay cursor when AG-UI reconnects", async () => {
    const { result } = renderHook(() => useChatStream("run-1"));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    const source = FakeEventSource.last!;
    expect(source.url).toContain("protocol=ag-ui");
    act(() => {
      source.send({ type: "TEXT_MESSAGE_CHUNK", messageId: "m", role: "assistant", delta: "Ready", rawEvent: { index: 0 } });
      source.send({ type: "CUSTOM", name: "resume.settled", value: {}, rawEvent: { index: 1 } });
      source.onerror?.();
    });
    await waitFor(() => expect(FakeEventSource.last!.url).toContain("offset=2"));
    expect(result.current.status).toBe("settled");
    expect(result.current.parts).toEqual([{ kind: "text", text: "Ready" }]);
    act(() => {
      FakeEventSource.last!.send({ type: "TEXT_MESSAGE_CHUNK", messageId: "m", role: "assistant", delta: "Ready", rawEvent: { index: 0 } });
      FakeEventSource.last!.send({ type: "RUN_FINISHED", runId: "run-1", threadId: "s", rawEvent: { index: 2 } });
    });
    expect(result.current.parts).toHaveLength(1);
    expect(result.current.status).toBe("done");
  });

  it.each(["stop", "reset"] as const)("%s cancels a scheduled reconnect and ignores late events", async (action) => {
    const { result } = renderHook(() => useChatStream("run-1"));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    const previous = FakeEventSource.last!;
    act(() => previous.onerror?.());
    act(() => result.current[action]());
    act(() => previous.send({ i: 0, t: "text", v: { text: "late" } }));
    await act(() => new Promise((resolve) => setTimeout(resolve, 550)));
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(result.current.parts).toEqual([]);
    expect(result.current.status).toBe("idle");
  });

  it("ignores events from a previous run", async () => {
    const { result, rerender } = renderHook(({ id }) => useChatStream(id), {
      initialProps: { id: "run-1" },
    });
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    const previous = FakeEventSource.last!;
    rerender({ id: "run-2" });
    await waitFor(() => expect(FakeEventSource.last?.url).toContain("run-2"));
    act(() => previous.send({ i: 0, t: "text", v: { text: "old run" } }));
    act(() => FakeEventSource.last!.send({ i: 0, t: "text", v: { text: "new run" } }));
    expect(result.current.parts).toEqual([{ kind: "text", text: "new run" }]);
  });

  it("does not connect if stopped while a link token is loading", async () => {
    localStorage.removeItem("resume-tailor-harness-token");
    let release!: () => void;
    const ready = new Promise<void>((resolve) => { release = resolve; });
    let requested = false;
    server.use(http.post("/api/auth/link-token", async () => {
      requested = true;
      await ready;
      return HttpResponse.json({ token: "late-token", expiresInSeconds: 60 });
    }));
    const { result } = renderHook(() => useChatStream("run-1"));
    await waitFor(() => expect(requested).toBe(true));
    act(() => result.current.stop());
    release();
    await getSseLinkToken();
    expect(FakeEventSource.instances).toHaveLength(0);
    expect(result.current.status).toBe("idle");
  });

  it("opens only one stream under Strict Mode and closes it on unmount", async () => {
    const { unmount } = renderHook(() => useChatStream("run-1"), {
      wrapper: ({ children }) => createElement(StrictMode, null, children),
    });
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    unmount();
    expect(FakeEventSource.last!.closed).toBe(true);
  });

  it("reuses one unexpired link token across consecutive runs", async () => {
    localStorage.removeItem("resume-tailor-harness-token");
    let requests = 0;
    server.use(http.post("/api/auth/link-token", () => {
      requests += 1;
      return HttpResponse.json({ token: "shared-link", expiresInSeconds: 60 });
    }));
    const { rerender } = renderHook(({ id }) => useChatStream(id), {
      initialProps: { id: "run-1" as string | null },
    });
    await waitFor(() => expect(FakeEventSource.last?.url).toContain("token=shared-link"));
    rerender({ id: "run-2" });
    await waitFor(() => expect(FakeEventSource.last?.url).toContain("run-2"));
    expect(requests).toBe(1);
  });

  it("re-mints a cached token once when its first connection fails", async () => {
    localStorage.removeItem("resume-tailor-harness-token");
    let requests = 0;
    server.use(http.post("/api/auth/link-token", () => {
      requests += 1;
      return HttpResponse.json({ token: `link-${requests}`, expiresInSeconds: 60 });
    }));
    renderHook(() => useChatStream("run-1"));
    await waitFor(() => expect(FakeEventSource.last?.url).toContain("token=link-1"));
    act(() => FakeEventSource.last!.onerror?.());
    await waitFor(() => expect(FakeEventSource.last?.url).toContain("token=link-2"));
    expect(requests).toBe(2);
  });
});
import { getSseLinkToken, resetSseLinkTokenCache } from "@/lib/runs/linkToken";
import { server } from "@/test/server";
