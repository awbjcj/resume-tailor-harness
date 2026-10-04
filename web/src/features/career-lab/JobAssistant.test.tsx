import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { useRunStore, type RunRecord } from "@/lib/runs/store";
import { JobAssistantConversation } from "./JobAssistant";

const mocks = vi.hoisted(() => ({
  start: vi.fn(), send: vi.fn(), stop: vi.fn(),
  status: "streaming", session: null as Record<string, unknown> | null,
}));
vi.mock("./use-career-lab", () => ({
  useCareerLabSessions: () => ({ data: { sessions: [] }, isPending: false, isError: false }),
  useCareerLabSession: () => ({ data: mocks.session, isPending: false, isError: false }),
  useStartCareerLab: () => ({ mutateAsync: mocks.start, isPending: false }),
  useSendCareerLabMessage: () => ({ mutateAsync: mocks.send, isPending: false }),
}));
vi.mock("@/lib/chat/useChatStream", () => ({
  useChatStream: () => ({ status: mocks.status, parts: [], error: null, stop: mocks.stop, reset: vi.fn() }),
}));
vi.mock("@/components/TranscribeButton", () => ({ TranscribeButton: () => null }));

const view = () => <MemoryRouter><JobAssistantConversation jobId={7} jobLabel="Acme Engineer" versions={[]} /></MemoryRouter>;
const completed: RunRecord = { runId: "r", kind: "career-lab-turn", status: "succeeded", percent: 100, phase: "Done", current: 1, total: 1, etaText: null, result: { sessionId: "s" } };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.status = "streaming";
  mocks.session = null;
  mocks.start.mockResolvedValue({ runId: "r" });
  useRunStore.setState({ runs: {} });
});

it("starts a draft with only explicitly selected job context", async () => {
  render(view());
  await userEvent.type(screen.getByRole("textbox", { name: "Ask about this job" }), "Help with this role");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(mocks.start).toHaveBeenCalledWith(expect.objectContaining({ message: "Help with this role", context: { jobId: 7, resumeVersionId: undefined, profileSnapshot: undefined, offerApplicationIds: [] } }));
});

it("preserves a new composer draft typed while the previous response is saving", async () => {
  const { rerender } = render(view());
  const input = screen.getByRole("textbox", { name: "Ask about this job" });
  await userEvent.type(input, "First question");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  mocks.status = "settled";
  rerender(view());
  await userEvent.clear(input);
  await userEvent.type(input, "My next question");
  act(() => mocks.start.mock.calls[0][0].onDone(completed));
  expect(input).toHaveValue("My next question");
  expect(screen.getByRole("link", { name: "Open full workspace" })).toHaveAttribute("href", "/career-lab?session=s");
});

it("ignores a late completion after the user stops the run", async () => {
  render(view());
  await userEvent.type(screen.getByRole("textbox", { name: "Ask about this job" }), "First question");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await userEvent.click(await screen.findByRole("button", { name: "Stop generating" }));
  act(() => mocks.start.mock.calls[0][0].onDone(completed));
  expect(mocks.stop).toHaveBeenCalledOnce();
  expect(screen.queryByRole("link", { name: "Open full workspace" })).not.toBeInTheDocument();
});
