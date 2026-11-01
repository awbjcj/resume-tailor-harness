import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { WorkspaceReview } from "./WorkspaceReview";

function proposal(expiresAt = "2099-01-01T00:00:00Z") {
  return { id: "p1", title: "Recruiter preparation", digest: "a".repeat(64), surface: "coach", sessionId: "s1", createdAt: "2026-11-01T00:00:00Z", expiresAt,
    actions: [1, 2].map((id) => ({ id: `a${id}`, change: { operation: "note.create", job_id: id, target_id: null, values: { title: `Note ${id}`, body: "Practice ownership" }, reason: "Keep preparation", citations: ["https://example.com/role"] }, before: null, after: { title: `Note ${id}`, body: "Practice ownership" }, receipt: null })) };
}

describe("WorkspaceReview", () => {
  it("keeps the exact proposal read-only until the human approves selected actions", async () => {
    const user = userEvent.setup();
    const saved = proposal();
    const requests: unknown[] = [];
    server.use(
      http.get("/api/workspace-agent/proposals", () => HttpResponse.json({ proposals: [saved], nextOffset: null })),
      http.post("/api/workspace-agent/proposals/p1/review", async ({ request }) => { requests.push(await request.json()); return HttpResponse.json(saved); }),
    );
    const { container } = render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    await screen.findByText("Recruiter preparation");
    expect(requests).toEqual([]);
    expect((await axe(container)).violations).toEqual([]);
    await user.click(screen.getAllByRole("checkbox")[1]);
    await user.click(screen.getByRole("button", { name: "Approve and save" }));
    await waitFor(() => expect(requests).toEqual([{ digest: saved.digest, actionIds: ["a1"], decision: "apply" }]));
  });

  it("allows discarding expired proposals while disabling approval", async () => {
    const user = userEvent.setup();
    const saved = proposal("2020-01-01T00:00:00Z");
    const requests: unknown[] = [];
    server.use(
      http.get("/api/workspace-agent/proposals", () => HttpResponse.json({ proposals: [saved], nextOffset: null })),
      http.post("/api/workspace-agent/proposals/p1/review", async ({ request }) => { requests.push(await request.json()); return HttpResponse.json(saved); }),
    );
    render(<WorkspaceReview surface="coach" sessionId="s1" />, { wrapper: withQueryClient });
    expect(await screen.findByRole("button", { name: "Approve and save" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(requests).toEqual([{ digest: saved.digest, actionIds: ["a1", "a2"], decision: "discard" }]));
  });
});
