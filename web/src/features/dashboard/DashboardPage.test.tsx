import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { DashboardPage } from "./DashboardPage";
import { SUMMARY } from "./fixtures";

const READY_STATUS = {
  secrets: { anthropicKey: true, anyLlmKey: true },
  profile: {
    documentCount: 1,
    hasResume: true,
    factsBuiltAt: "2026-07-01T00:00:00Z",
    githubUsername: null,
  },
  search: { configured: true },
  sources: { enabledCount: 2 },
  complete: true,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
    { wrapper: withQueryClient },
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    server.use(http.get("/api/notifications", () => HttpResponse.json([])));
  });

  it("shows application approvals even when the pipeline queues are empty", async () => {
    server.use(
      http.get("/api/dashboard/summary", () => HttpResponse.json({
        ...SUMMARY,
        statusCounts: {},
        queues: { triage: 0, approve: 0, tailor: 0, apply: 0 },
      })),
      http.get("/api/setup/status", () => HttpResponse.json(READY_STATUS)),
      http.get("/api/notifications", () => HttpResponse.json([{
        id: 3, applicationId: 1, jobId: 7, company: "Acme", title: "Engineer",
        kind: "rejected", proposedStatus: "rejected", evidence: "Thank you for applying.",
        messageId: "rejection", state: "pending", revision: "r1", createdAt: "2026-10-23T12:00:00Z",
      }])),
      http.post("/api/gmail/sync", () => HttpResponse.json({
        error: { code: "GMAIL_NOT_CONNECTED", message: "Connect Gmail in Settings before syncing" },
      }, { status: 409 })),
    );
    const user = userEvent.setup();
    renderPage();
    const board = within(await screen.findByRole("region", { name: "Application notifications" }));
    expect(screen.getByRole("heading", { name: "No jobs waiting in the pipeline" })).toBeInTheDocument();
    expect(await board.findByText("Move to Rejected")).toBeInTheDocument();
    expect(board.getByRole("button", { name: "Approve" })).toBeEnabled();
    expect(board.getByRole("button", { name: "Reject update" })).toBeEnabled();
    expect(board.getByRole("button", { name: "Review cleared Gmail updates" })).toBeEnabled();
    await user.click(board.getByRole("button", { name: "Sync Gmail" }));
    expect(await board.findByRole("alert")).toHaveTextContent("Connect Gmail in Settings before syncing");
  });

  it("renders hero total, queue cards, and stage rail from the summary", async () => {
    server.use(
      http.get("/api/dashboard/summary", () => HttpResponse.json(SUMMARY)),
      http.get("/api/setup/status", () => HttpResponse.json(READY_STATUS)),
    );
    renderPage();
    // queues sum: 2 + 4 + 1 + 1
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "8 jobs are waiting on you" }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("link", { name: /approve 4/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Pipeline stages")).toBeInTheDocument();
    expect(screen.getByText(/recent runs/i)).toBeInTheDocument();
    const shortcuts = within(screen.getByRole("navigation", { name: /workspace shortcuts/i }));
    expect(shortcuts.getByRole("link", { name: /sources/i })).toHaveAttribute("href", "/settings/sources");
    expect(shortcuts.getByRole("link", { name: /search settings/i })).toHaveAttribute("href", "/settings/search");
    expect(shortcuts.getByRole("link", { name: /review workflow/i })).toHaveAttribute("href", "/settings/review");
    expect(shortcuts.getByRole("link", { name: /profile skills/i })).toHaveAttribute("href", "/profile?tab=skills");
    expect(shortcuts.getByRole("link", { name: /api keys/i })).toHaveAttribute("href", "/settings/keys");
    expect(shortcuts.queryByRole("link", { name: /triage/i })).not.toBeInTheDocument();
    expect(shortcuts.queryByRole("link", { name: /shortlist/i })).not.toBeInTheDocument();
    expect(shortcuts.queryByRole("link", { name: /pipeline/i })).not.toBeInTheDocument();
    const firstQueueLink = screen.getByRole("link", { name: /triage 2/i });
    expect(
      firstQueueLink.compareDocumentPosition(
        shortcuts.getByRole("link", { name: /sources/i }),
      ),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("guides a fresh install with one journey and an actionable next step", async () => {
    const zero = Object.fromEntries(
      Object.keys(SUMMARY.statusCounts).map((k) => [k, 0]),
    );
    server.use(
      http.get("/api/dashboard/summary", () =>
        HttpResponse.json({
          statusCounts: zero,
          queues: { triage: 0, approve: 0, tailor: 0, apply: 0 },
          applied: 0,
        }),
      ),
      http.get("/api/setup/status", () =>
        HttpResponse.json({
          ...READY_STATUS,
          complete: false,
          sources: { enabledCount: 0 },
        }),
      ),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Job-search journey")).toBeInTheDocument(),
    );
    const sourceLinks = screen.getAllByRole("link", { name: /add sources/i });
    expect(sourceLinks).toHaveLength(1);
    expect(sourceLinks[0]).toHaveAttribute("href", "/settings/sources");
    expect(screen.queryByText("Getting started")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Pipeline stages")).not.toBeInTheDocument();
  });

  it("does not treat an only-rejected funnel as populated", async () => {
    // rejected doesn't appear on the rail/queues, so a naive "sum every
    // statusCount" emptiness check would wrongly treat this as populated. Even
    // for a set-up user, an all-rejected funnel has no active jobs, so the
    // funnel view stays hidden and guidance points forward instead.
    server.use(
      http.get("/api/dashboard/summary", () =>
        HttpResponse.json({
          statusCounts: {
            raw: 0, extracted: 0, filtered: 0, rejected: 5,
            shortlisted: 0, approved: 0, tailored: 0, rendered: 0,
          },
          queues: { triage: 0, approve: 0, tailor: 0, apply: 0 },
          applied: 0,
        }),
      ),
      http.get("/api/setup/status", () => HttpResponse.json(READY_STATUS)),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Job-search journey")).toBeInTheDocument(),
    );
    expect(screen.queryByLabelText("Pipeline stages")).not.toBeInTheDocument();
  });
});
