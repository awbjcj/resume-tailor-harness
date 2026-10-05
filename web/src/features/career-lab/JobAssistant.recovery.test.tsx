import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useRunCompletionEffects } from "@/features/runs/use-run-completion-effects";
import { resetInvalidationForTests } from "@/lib/runs/invalidation";
import { useRunStore, type RunRecord } from "@/lib/runs/store";
import { completeRuns, resetRunTrackerForTests } from "@/lib/runs/tracker";
import { server } from "@/test/server";
import { JobAssistantConversation } from "./JobAssistant";

// Keep session queries, recovery selection and completion effects real. The
// stream intentionally clears when recovery drops the terminal run's id.
vi.mock("@/lib/chat/useChatStream", () => ({
  useChatStream: (runId: string | null) => ({
    status: runId ? "streaming" : "idle", error: null,
    parts: runId ? [{ kind: "text", text: "Unsaved streamed response" }] : [],
    stop: vi.fn(), reset: vi.fn(),
  }),
}));
vi.mock("@/components/TranscribeButton", () => ({ TranscribeButton: () => null }));

function RecoveredConversation() {
  useRunCompletionEffects();
  return <JobAssistantConversation jobId={7} jobLabel="Acme Engineer" versions={[]} />;
}

beforeEach(() => {
  resetRunTrackerForTests();
  resetInvalidationForTests();
  useRunStore.setState({ runs: {} });
});
afterEach(() => resetRunTrackerForTests());

it.each([false, true])("loads the saved response after a recovered run completes (existing session: %s)", async (existing) => {
  const summary = {
    sessionId: "recovered-session", title: "Job discussion", goal: "Discuss Acme",
    startedAt: "2026-10-04T12:00:00Z", endedAt: null, archivedAt: null,
    status: "active", jobId: 7, jobCompany: "Acme", jobTitle: "Engineer",
  };
  const previousTurns = existing ? [
    { turnId: "old-user", role: "user", text: "Earlier question" },
    { turnId: "old-assistant", role: "assistant", text: "Earlier answer" },
  ] : [];
  let saved = false;
  server.use(
    http.get("/api/career-lab/sessions", () => {
      const sessions = existing || saved ? [{ ...summary, turnCount: saved ? previousTurns.length + 2 : previousTurns.length }] : [];
      return HttpResponse.json({ sessions, activeSessions: sessions, pagination: { page: 1, pageSize: 20, totalItems: sessions.length, totalPages: 1 } });
    }),
    http.get("/api/career-lab/sessions/recovered-session", () => HttpResponse.json({
      ...summary,
      turns: saved ? [...previousTurns,
        { turnId: "new-user", role: "user", text: "Question before reload" },
        { turnId: "new-assistant", role: "assistant", text: "Saved answer after reload" },
      ] : previousTurns,
    })),
    http.post("/api/runs/ack", () => HttpResponse.json({ acknowledged: 1 })),
  );
  const recovered: RunRecord = {
    runId: "recovered-run", kind: "career-lab-turn", status: "running",
    percent: 20, phase: "Drafting", current: 1, total: 2, etaText: null,
    meta: { jobId: 7, turnCount: previousTurns.length, ...(existing ? { sessionId: summary.sessionId } : {}) },
  };
  // A reload restores the run but loses the launching mutation's callback.
  useRunStore.getState().upsert(recovered);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const { unmount } = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><RecoveredConversation /></MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(queryClient.getQueryState(["career-lab-sessions", false, 1, 20, 7])?.status).toBe("success"));
  if (existing) await screen.findByText("Earlier answer");
  expect(screen.getByText("Unsaved streamed response")).toBeVisible();
  if (!existing) expect(screen.queryByRole("link", { name: "Open full workspace" })).not.toBeInTheDocument();

  saved = true;
  act(() => completeRuns([{ ...recovered, status: "succeeded", percent: 100, result: { sessionId: summary.sessionId } }]));

  expect(await screen.findByText("Saved answer after reload")).toBeVisible();
  expect(screen.getByText("Question before reload")).toBeVisible();
  expect(screen.queryByText("Unsaved streamed response")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open full workspace" })).toHaveAttribute("href", "/career-lab?session=recovered-session");
  expect(screen.getByRole("textbox", { name: "Ask about this job" })).toBeEnabled();
  // The persisted answer survives retirement of the temporary run record.
  act(() => useRunStore.getState().remove(recovered.runId));
  expect(screen.getByText("Saved answer after reload")).toBeVisible();
  unmount();
  queryClient.clear();
});
