import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import type { components } from "@/lib/api/schema";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { WorkspaceReview } from "./WorkspaceReview";
import { WorkspaceProposalCard } from "./workspace-review/WorkspaceProposalCard";

type Proposal = components["schemas"]["ProposalOut"];

function proposal(): Proposal {
  return {
    id: "p1", title: "Recruiter preparation", digest: "a".repeat(64), surface: "coach", sessionId: "s1",
    createdAt: "2026-11-01T00:00:00Z", expiresAt: "2099-01-01T00:00:00Z",
    actions: [1, 2].map((id) => ({
      id: `a${id}`, change: { operation: "note.create", job_id: id, target_id: null, values: {}, reason: "Keep preparation", citations: [] },
      before: null, after: { title: `Note ${id}`, body: "Practice ownership" }, receipt: null,
    })),
  };
}

function serve(saved = proposal()) {
  server.use(http.get("/api/workspace-agent/proposals", () => HttpResponse.json({ proposals: [saved], nextOffset: null })));
  return saved;
}

describe("workspace review interactions", () => {
  it("shows progress, prevents repeat submissions, and preserves the unselected action after a partial save", async () => {
    const user = userEvent.setup();
    const saved = serve();
    let finish!: () => void;
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    const requests: unknown[] = [];
    server.use(http.post("/api/workspace-agent/proposals/p1/review", async ({ request }) => {
      requests.push(await request.json());
      await pending;
      saved.actions[0].receipt = { state: "applied", result: { noteId: 1 }, approvedBy: "local-user", createdAt: saved.createdAt };
      return HttpResponse.json(saved);
    }));
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    await user.click(await screen.findByRole("checkbox", { name: /Add note.*#2/ }));
    await user.click(screen.getByRole("button", { name: "Approve and save" }));
    expect(await screen.findByText("Saving selected changes…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve and save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard" })).toBeDisabled();
    for (const checkbox of screen.getAllByRole("checkbox")) expect(checkbox).toHaveAttribute("aria-disabled", "true");
    finish();
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("checkbox", { name: /Add note.*#2/ })).not.toHaveAttribute("aria-disabled", "true"));
    expect(screen.getByRole("checkbox", { name: /Add note.*#2/ })).not.toBeChecked();
    expect(screen.getByText("Selected 0 of 1 changes")).toBeInTheDocument();
    expect(requests).toEqual([{ digest: saved.digest, actionIds: ["a1"], decision: "apply" }]);
  });

  it("keeps the previous-page control available when the next page is empty", async () => {
    const user = userEvent.setup();
    server.use(http.get("/api/workspace-agent/proposals", ({ request }) => {
      const offset = Number(new URL(request.url).searchParams.get("offset"));
      return HttpResponse.json({ proposals: offset ? [] : [proposal()], nextOffset: offset ? null : 20 });
    }));
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    await user.click(await screen.findByRole("button", { name: "Next" }));
    expect(await screen.findByText("No more proposed changes.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText("Recruiter preparation")).toBeInTheDocument();
  });

  it("keeps review choices and displays an inline error when approval fails", async () => {
    const user = userEvent.setup();
    serve();
    server.use(http.post("/api/workspace-agent/proposals/p1/review", () => HttpResponse.json({
      error: { code: "WORKSPACE_REVIEW_CONFLICT", message: "The preview changed. Request a new proposal." },
    }, { status: 409 })));
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    await user.click(await screen.findByRole("checkbox", { name: /Add note.*#2/ }));
    await user.click(screen.getByRole("button", { name: "Approve and save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ask the agent for a new preview");
    expect(screen.getByRole("button", { name: "Approve and save" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /Add note.*#2/ })).not.toBeChecked();
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
  });

  it("recovers from a failed initial load using Retry", async () => {
    const user = userEvent.setup();
    let failed = true;
    server.use(http.get("/api/workspace-agent/proposals", () => failed
      ? HttpResponse.json({}, { status: 500 })
      : HttpResponse.json({ proposals: [proposal()], nextOffset: null })));
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load proposed changes.");
    failed = false;
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Recruiter preparation")).toBeInTheDocument();
  });

  it("localizes review controls while preserving exact values and rendering unsafe citations as text", async () => {
    await changeLanguage("zh-CN");
    const saved = proposal();
    saved.actions = [saved.actions[0]];
    saved.actions[0].after = { title: "Original title", empty: "", list: [], object: {}, flag: false, count: 0 };
    saved.actions[0].change.citations = ["javascript:alert(1)", "https://example.com/evidence"];
    serve(saved);
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    const review = await screen.findByRole("region", { name: "工作区更改" });
    expect(await within(review).findByText("Original title")).toBeInTheDocument();
    expect(within(review).getByText("否")).toBeInTheDocument();
    expect(within(review).getByText("0")).toBeInTheDocument();
    expect(within(review).getByText("无条目")).toBeInTheDocument();
    expect(within(review).getByText("空文本")).toBeInTheDocument();
    expect(within(review).getByText("无字段")).toBeInTheDocument();
    expect(within(review).getByText("已选择 1 项更改，共 1 项")).toBeInTheDocument();
    expect(within(review).getAllByRole("link")).toHaveLength(1);
    expect(within(review).getByText("javascript:alert(1)")).not.toHaveAttribute("href");
  });

  it("blocks approval at the exact expiry while keeping discard selection available", () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date("2026-11-01T00:00:00Z"));
      const saved = proposal();
      saved.expiresAt = "2026-11-01T00:00:01";
      const view = render(<WorkspaceProposalCard proposal={saved} />, { wrapper: withQueryClient });
      expect(screen.getByRole("button", { name: "Approve and save" })).toBeEnabled();
      act(() => vi.advanceTimersByTime(1000));
      expect(screen.getByRole("button", { name: "Approve and save" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Discard" })).toBeEnabled();
      expect(screen.getAllByRole("checkbox")[0]).toBeEnabled();
      view.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows an unconfirmed receipt without offering another approval", async () => {
    const saved = proposal();
    saved.actions = [saved.actions[0]];
    saved.actions[0].receipt = { state: "unconfirmed", result: {}, approvedBy: "local-user", createdAt: saved.createdAt };
    serve(saved);
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    expect((await screen.findAllByText("Outcome unconfirmed. Check the saved record; do not retry this change.")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve and save" })).not.toBeInTheDocument();
  });

  it("leaves deletions unselected and requires confirmation before sending the exact selected actions", async () => {
    const user = userEvent.setup();
    const saved = proposal();
    saved.actions[1].change.operation = "job.delete";
    saved.actions[1].before = { title: "Duplicate role" };
    saved.actions[1].after = { deleted: true };
    serve(saved);
    const requests: unknown[] = [];
    server.use(http.post("/api/workspace-agent/proposals/p1/review", async ({ request }) => {
      requests.push(await request.json());
      for (const action of saved.actions) action.receipt = { state: "applied", result: {}, approvedBy: "local-user", createdAt: saved.createdAt };
      return HttpResponse.json(saved);
    }));
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    const deletion = await screen.findByRole("checkbox", { name: /Delete job.*#2/ });
    expect(deletion).not.toBeChecked();
    expect(screen.getByText("Selected 1 of 2 changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select all" }));
    expect(deletion).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Approve and save" }));
    let dialog = await screen.findByRole("alertdialog");
    expect(requests).toEqual([]);
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Back to review" })).toHaveFocus());
    await user.click(within(dialog).getByRole("button", { name: "Back to review" }));
    expect(deletion).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Approve and save" }));
    dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Duplicate role")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Save and remove" }));
    await waitFor(() => expect(requests).toEqual([{ digest: saved.digest, actionIds: ["a1", "a2"], decision: "apply" }]));
    expect(await screen.findByText("All changes have been reviewed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve and save" })).not.toBeInTheDocument();
  });

  it("clears and restores selection without submitting a review", async () => {
    const user = userEvent.setup();
    serve();
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    await user.click(await screen.findByRole("button", { name: "Clear selection" }));
    for (const checkbox of screen.getAllByRole("checkbox")) expect(checkbox).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Approve and save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Select all" }));
    for (const checkbox of screen.getAllByRole("checkbox")) expect(checkbox).toBeChecked();
  });

  it("also leaves profile-content removals unselected", async () => {
    const saved = proposal();
    saved.actions = [saved.actions[0]];
    saved.actions[0].change.operation = "profile.change";
    saved.actions[0].before = [{ name: "Python" }];
    saved.actions[0].after = [null];
    serve(saved);
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    expect(await screen.findByRole("checkbox", { name: /Update profile/ })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Approve and save" })).toBeDisabled();
    expect(screen.getByText(/removes profile content/)).toBeInTheDocument();
  });

  it("translates nested schema fields and known enums while retaining user-authored values", async () => {
    await changeLanguage("zh-CN");
    const saved = proposal();
    saved.actions = [saved.actions[0]];
    const after = {
      legalName: { givenName: "Alex", familyName: "Li" },
      work_eligibility: [{ authorized_to_work: false, sponsorship_now: true }],
      employer_answers: [{ category: "role_requirement", answer: "general" }],
      experienceRanges: [{ minimumYears: 0, maximumYears: 3 }],
    };
    saved.actions[0].change.operation = "application_profile.update";
    saved.actions[0].after = after;
    serve(saved);
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    expect(await screen.findByText("法定姓名")).toBeInTheDocument();
    expect(screen.getByText("具有合法工作资格")).toBeInTheDocument();
    expect(screen.getByText("否")).toBeInTheDocument();
    expect(screen.getByText("答案类别")).toBeInTheDocument();
    expect(screen.getByText("职位要求")).toBeInTheDocument();
    expect(screen.getByText("general")).toBeInTheDocument();
    expect(screen.getByText("最少年数")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(saved.actions[0].after).toEqual(after);
  });
});
