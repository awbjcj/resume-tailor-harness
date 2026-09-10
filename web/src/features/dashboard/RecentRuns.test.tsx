import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { useRunStore } from "@/lib/runs/store";
import { changeLanguage } from "@/i18n";
import { RecentRuns } from "./RecentRuns";

const completed = { id: 1, runId: "saved", kind: "discover", label: "Imported sources",
  status: "succeeded", error: null, completedAt: "2026-09-09T12:00:00Z", readAt: null };

describe("RecentRuns durable history", () => {
  afterEach(async () => {
    useRunStore.setState({ runs: {} });
    await changeLanguage("en");
  });

  it("shows saved operations without a live store, expands logs, and clears only completed history", async () => {
    let cleared = false;
    server.use(
      http.get("*/api/run-completions", ({ request }) => {
        expect(new URL(request.url).searchParams.get("surface")).toBe("operations");
        return HttpResponse.json(cleared ? [] : [completed]);
      }),
      http.get("*/api/run-completions/1/logs", () => HttpResponse.json([
        { timestamp: "2026-09-09T12:00:00Z", message: "Reading source documents", state: "running" },
      ])),
      http.delete("*/api/run-completions", () => { cleared = true; return HttpResponse.json({ cleared: 1 }); }),
    );
    useRunStore.getState().upsert({ runId: "active", kind: "pull", status: "running", percent: 20,
      phase: "Pulling", current: 1, total: 5, etaText: null });
    const user = userEvent.setup();
    const view = render(<RecentRuns />, { wrapper: withQueryClient });
    expect(await screen.findByText("Imported sources")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("Job pull");
    await user.click(screen.getByRole("button", { name: "View logs" }));
    expect(await screen.findByText("Reading source documents")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear operation history" }));
    await user.click(screen.getByRole("button", { name: "Keep history" }));
    expect(cleared).toBe(false);
    await user.click(screen.getByRole("button", { name: "Clear operation history" }));
    await user.click(screen.getByRole("button", { name: "Clear history" }));
    await waitFor(() => expect(screen.queryByText("Imported sources")).not.toBeInTheDocument());
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    view.unmount();
    render(<RecentRuns />, { wrapper: withQueryClient });
    expect(await screen.findByText("No completed operations in your history.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("keeps history visible when clearing fails", async () => {
    server.use(
      http.get("*/api/run-completions", () => HttpResponse.json([completed])),
      http.delete("*/api/run-completions", () => HttpResponse.json({ error: { message: "Unavailable" } }, { status: 500 })),
    );
    const user = userEvent.setup();
    render(<RecentRuns />, { wrapper: withQueryClient });
    await screen.findByText("Imported sources");
    await user.click(screen.getByRole("button", { name: "Clear operation history" }));
    await user.click(screen.getByRole("button", { name: "Clear history" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not clear history");
    expect(screen.getByText("Imported sources")).toBeInTheDocument();
  });
});


it("localizes active names, phases, and history controls in Chinese", async () => {
  await changeLanguage("zh-CN");
  server.use(http.get("*/api/run-completions", () => HttpResponse.json([])));
  useRunStore.getState().upsert({ runId: "profile", kind: "profile-build", status: "running",
    percent: 10, phase: "Extracting and merging source documents", current: 0, total: 1, etaText: null });
  try {
    render(<RecentRuns />, { wrapper: withQueryClient });
    expect(screen.getByText(/个人资料构建 · 正在提取并合并源文档/)).toBeInTheDocument();
    expect(await screen.findByText("历史中暂无已完成的操作。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "清空操作历史" })).toBeInTheDocument();
  } finally {
    useRunStore.setState({ runs: {} });
    await changeLanguage("en");
  }
});
