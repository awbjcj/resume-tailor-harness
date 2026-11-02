import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { OperationHistory } from "@/features/dashboard/OperationHistory";
import { NotificationsBell } from "@/features/notifications/NotificationsBell";

vi.mock("@/features/job/EmailDraftDialog", () => ({ EmailDraftDialog: () => null }));

const completed = {
  id: 7, runId: "tailored", kind: "tailor", status: "succeeded", label: "Done",
  completedAt: "2026-11-02T12:00:00Z", readAt: null, error: null,
  resultHref: "/pipeline?job=4&tab=tracking", resultAvailable: true,
};

describe("completed work continuation", () => {
  it("keeps a server-resolved result link after reload and leaves logs independent", async () => {
    let writes = 0;
    server.use(
      http.get("/api/run-completions", () => HttpResponse.json([completed])),
      http.get("/api/run-completions/7/logs", () => HttpResponse.json([{ timestamp: completed.completedAt, message: "Saved revision" }])),
      http.post("/api/tailor", () => { writes++; return HttpResponse.json({}); }),
    );
    render(<MemoryRouter><OperationHistory /></MemoryRouter>, { wrapper: withQueryClient });
    expect(await screen.findByRole("link", { name: "Open result" })).toHaveAttribute("href", completed.resultHref);
    fireEvent.click(screen.getByRole("button", { name: "View logs" }));
    expect(await screen.findByText("Saved revision")).toBeInTheDocument();
    expect(writes).toBe(0);
  });

  it("labels an unavailable historical target as workspace navigation in Chinese", async () => {
    await changeLanguage("zh-CN");
    server.use(http.get("/api/run-completions", () => HttpResponse.json([{ ...completed, resultHref: "/pipeline", resultAvailable: false }])));
    render(<MemoryRouter><OperationHistory /></MemoryRouter>, { wrapper: withQueryClient });
    expect(await screen.findByRole("link", { name: "打开工作区" })).toHaveAttribute("href", "/pipeline");
    expect(screen.queryByRole("link", { name: "查看结果" })).not.toBeInTheDocument();
  });

  it("offers the same result destination from durable notification history", async () => {
    server.use(
      http.get("/api/run-completions", () => HttpResponse.json([completed])),
      http.get("/api/notifications", () => HttpResponse.json([])),
    );
    render(<MemoryRouter><NotificationsBell /></MemoryRouter>, { wrapper: withQueryClient });
    await userEvent.click(screen.getByRole("button", { name: /Notifications/ }));
    expect(await screen.findByRole("link", { name: "Open result" })).toHaveAttribute("href", completed.resultHref);
  });
});
