import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { useRunCompletionEffects } from "./use-run-completion-effects";
import { completeRuns, resetRunTrackerForTests } from "@/lib/runs/tracker";
import { useRunStore, type RunRecord } from "@/lib/runs/store";

const mocks = vi.hoisted(() => ({
  ack: vi.fn().mockResolvedValue(undefined),
  success: vi.fn(), error: vi.fn(), info: vi.fn(),
}));
vi.mock("@/lib/runs/ack", () => ({ ackRuns: mocks.ack }));
vi.mock("sonner", () => ({ toast: mocks }));

beforeEach(() => {
  vi.clearAllMocks();
  resetRunTrackerForTests();
  useRunStore.setState({ runs: {} });
});

it("acks quiet chat runs, refreshes their conversations and announces a failure only once", async () => {
  const qc = new QueryClient();
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  renderHook(() => useRunCompletionEffects(), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  });
  const runs: RunRecord[] = (["succeeded", "cancelled", "failed"] as const).map((status) => ({
    runId: status, kind: "career-lab-turn", status,
    percent: 100, phase: "", current: 1, total: 1, etaText: null, error: "boom",
  }));
  act(() => completeRuns(runs));
  await waitFor(() => expect(mocks.ack).toHaveBeenCalledWith(["succeeded", "cancelled", "failed"]));
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["career-lab-sessions"] });
  expect(mocks.success).not.toHaveBeenCalled();
  expect(mocks.info).not.toHaveBeenCalled();
  expect(mocks.error).toHaveBeenCalledOnce();
  act(() => completeRuns(runs));
  expect(mocks.error).toHaveBeenCalledOnce();
});
