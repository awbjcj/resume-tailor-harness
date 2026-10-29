import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { useRunStore, type RunRecord } from "@/lib/runs/store";
import { watchRun } from "@/lib/runs/sse";
import { useAcceptNotification, useGmailSync } from "./use-notifications";

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

  it("requests cleared updates only when explicitly selected", async () => {
    const bodies: unknown[] = [];
    server.use(http.post("*/api/gmail/sync", async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json({ runId: "recovery", kind: "gmailSync", state: "running" }, { status: 202 });
    }));
    const { result } = renderHook(() => useGmailSync(), { wrapper: withQueryClient });
    await act(async () => { await result.current.mutateAsync({ reviewCleared: true }); });
    expect(bodies).toEqual([{ reviewCleared: true }]);
  });
});

it("refreshes application status across views after accepting a Gmail update", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const keys = [
    ["notifications"], ["applications", { status: "submitted" }], ["job", 7],
    ["pipeline"], ["dashboard-summary"], ["analytics-timeline"],
  ];
  keys.forEach((key) => qc.setQueryData(key, { status: "submitted" }));
  qc.setQueryData(["settings"], {});
  server.use(http.post("*/api/notifications/1/accept", () => HttpResponse.json({ state: "accepted" })));
  const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useAcceptNotification(), { wrapper });
  await act(async () => { await result.current.mutateAsync(1); });
  for (const key of keys) expect(qc.getQueryState(key)?.isInvalidated).toBe(true);
  expect(qc.getQueryState(["settings"])?.isInvalidated).toBe(false);
});
