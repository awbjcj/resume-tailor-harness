import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { useRunStore, type RunRecord } from "@/lib/runs/store";
import { watchRun } from "@/lib/runs/sse";
import { useGmailSync } from "./use-notifications";

vi.mock("@/lib/runs/sse", () => ({ watchRun: vi.fn() }));

describe("useGmailSync", () => {
  afterEach(() => {
    useRunStore.setState({ runs: {} });
    vi.clearAllMocks();
  });

  it("stays busy after launch until the background run reaches a terminal state", async () => {
    server.use(http.post("*/api/gmail/sync", () => HttpResponse.json({
      runId: "gmail-run", kind: "gmailSync", state: "running",
    }, { status: 202 })));
    const { result } = renderHook(() => useGmailSync(), { wrapper: withQueryClient });
    await act(async () => { await result.current.mutateAsync(); });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isPending).toBe(true);
    const done: RunRecord = {
      ...useRunStore.getState().runs["gmail-run"], status: "failed", error: "Reconnect Gmail",
    };
    act(() => {
      useRunStore.getState().upsert(done);
      vi.mocked(watchRun).mock.calls[0][2]?.(done);
    });
    await waitFor(() => expect(result.current.isPending).toBe(false));
  });

  it("also recognizes a scheduled sync already in progress", () => {
    useRunStore.getState().upsert({
      runId: "scheduled", kind: "gmailSync", status: "queued", percent: 0,
      phase: "", current: 0, total: 1, etaText: null,
    });
    const { result } = renderHook(() => useGmailSync(), { wrapper: withQueryClient });
    expect(result.current.isPending).toBe(true);
  });
});
