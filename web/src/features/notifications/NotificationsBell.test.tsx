import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { changeLanguage } from "@/i18n";
import { NotificationsBell } from "./NotificationsBell";
import { MemoryRouter } from "react-router-dom";

describe("NotificationsBell", () => {
  it.each(["Done with warnings", "Sync complete; more emails remain"])("shows sync completion detail: %s", async (label) => {
    server.use(
      http.get("*/api/notifications", () => HttpResponse.json([])),
      http.get("*/api/run-completions", () => HttpResponse.json([{
        id: 20, runId: "gmail-partial", kind: "gmailSync", label,
        status: "succeeded", error: null, completedAt: "2026-09-21T12:00:00Z", readAt: null,
      }])),
    );
    const user = userEvent.setup();
    render(<NotificationsBell />, { wrapper: withQueryClient });
    await user.click(await screen.findByRole("button", { name: /notifications/i }));
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  afterEach(async () => {
    await changeLanguage("en");
  });

  it("shows durable run history and counts only unread runs", async () => {
    server.use(
      http.get("*/api/notifications", () => HttpResponse.json([])),
      http.get("*/api/run-completions", () =>
        HttpResponse.json([
          {
            id: 11,
            runId: "run-11",
            kind: "discover",
            label: "Done",
            status: "succeeded",
            error: null,
            completedAt: "2026-08-29T12:00:00Z",
            readAt: null,
          },
          {
            id: 10,
            runId: "run-10",
            kind: "pull",
            label: "Done",
            status: "failed",
            error: "Provider unavailable",
            completedAt: "2026-08-29T11:00:00Z",
            readAt: "2026-08-29T11:30:00Z",
          },
        ]),
      ),
    );
    const user = userEvent.setup();
    render(<NotificationsBell />, { wrapper: withQueryClient });

    expect(await screen.findByRole("button", { name: /notifications \(1 pending\)/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /notifications/i }));

    expect(await screen.findByText("Discovery succeeded")).toBeInTheDocument();
    expect(screen.getByText("Job pull failed")).toBeInTheDocument();
    expect(screen.getByText("Provider unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark all read" })).toBeInTheDocument();
  });

  it("localizes dynamic run kinds, protocol statuses, and known backend errors", async () => {
    await changeLanguage("zh-CN");
    server.use(
      http.get("*/api/notifications", () => HttpResponse.json([])),
      http.get("*/api/run-completions", () =>
        HttpResponse.json([
          {
            id: 12,
            runId: "run-12",
            kind: "gmailSync",
            label: "Done",
            status: "failed",
            error: "GmailNotConnected: Gmail is not connected for this workspace",
            completedAt: "2026-08-29T12:00:00Z",
            readAt: null,
          },
        ]),
      ),
    );
    const user = userEvent.setup();
    render(<NotificationsBell />, { wrapper: withQueryClient });

    await user.click(await screen.findByRole("button", { name: /通知/i }));
    expect(await screen.findByText("Gmail 同步失败")).toBeInTheDocument();
    expect(screen.getByText("Gmail 尚未连接到此工作区。")).toBeInTheDocument();
    expect(screen.queryByText(/GmailNotConnected|is not connected for this workspace/)).not.toBeInTheDocument();
  });

  it("shows event reminders and excludes proposals and follow-ups from the bell and its count", async () => {
    server.use(
      http.get("*/api/notifications", () =>
        HttpResponse.json([
          {
            id: 8,
            applicationId: 3,
            kind: "interview_soon",
            proposedStatus: "",
            evidence: "Tomorrow at 2:00 PM: Acme · Staff Engineer",
            messageId: "event:22:2026-09-01T18:00:00Z",
            state: "pending",
            createdAt: "2026-08-31T18:00:00Z",
            jobId: 7,
            company: "Acme",
            title: "Staff Engineer",
          },
          { id: 9, kind: "follow_up", proposedStatus: "", company: "Followup Co" },
          { id: 10, kind: "rejected", proposedStatus: "rejected", evidence: "Thank you for applying" },
        ]),
      ),
      http.get("*/api/run-completions", () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <NotificationsBell />
      </MemoryRouter>,
      { wrapper: withQueryClient },
    );

    await user.click(screen.getByRole("button", { name: /notifications/i }));
    expect(await screen.findByText("Interview soon: Acme")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view job/i })).toHaveAttribute(
      "href",
      "/pipeline?job=7",
    );
    expect(screen.getByRole("button", { name: "Notifications (1 pending)" })).toBeInTheDocument();
    expect(screen.queryByText("Follow up: Followup Co")).not.toBeInTheDocument();
    expect(screen.queryByText("Thank you for applying")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve|reject update|dismiss|draft follow-up|sync gmail|cleared gmail/i })).not.toBeInTheDocument();
  });
});


it("clears run history after confirmation", async () => {
  let cleared = false;
  server.use(
    http.get("*/api/notifications", () => HttpResponse.json([])),
    http.get("*/api/run-completions", () => HttpResponse.json(cleared ? [] : [{
      id: 1, runId: "saved", kind: "discover", label: "Done", status: "succeeded",
      error: null, completedAt: "2026-09-09T12:00:00Z", readAt: null,
    }])),
    http.delete("*/api/notifications", () => { cleared = true; return HttpResponse.json({ cleared: 1 }); }),
  );
  const user = userEvent.setup();
  render(<NotificationsBell />, { wrapper: withQueryClient });
  await user.click(await screen.findByRole("button", { name: /notifications \(1 pending\)/i }));
  await user.click(screen.getByRole("button", { name: "Clear run history" }));
  await user.click(screen.getByRole("button", { name: "Clear history" }));
  expect(await screen.findByText("Nothing pending.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
});
