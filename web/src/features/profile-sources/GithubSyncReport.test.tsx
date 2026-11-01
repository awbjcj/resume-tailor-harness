import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { changeLanguage } from "@/i18n";
import { useRunStore } from "@/lib/runs/store";
import { GithubSyncReport } from "./GithubSyncReport";

describe("GitHub sync feedback", () => {
  beforeEach(() => useRunStore.setState({ runs: {} }));
  afterEach(async () => { await changeLanguage("en"); });
  it("makes partial sync failures and recovery visible and retains the report", () => {
    useRunStore.getState().upsert({ runId: "sync", kind: "github-sync", status: "succeeded", percent: 100,
      phase: "done", current: 1, total: 1, etaText: null,
      result: { written: [], failures: { "portfolio": "Branch feature/dossier was not found" }, warnings: [] } });
    render(<GithubSyncReport />);
    expect(screen.getByRole("alert")).toHaveTextContent("GitHub sync needs attention");
    expect(screen.getByRole("alert")).toHaveTextContent("saved copies are kept");
    expect(screen.getByRole("alert")).toHaveTextContent("feature/dossier");
    act(() => useRunStore.getState().remove("sync"));
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("localizes known sync diagnostics while preserving branch names and unknown details", async () => {
    await changeLanguage("zh-CN");
    useRunStore.getState().upsert({ runId: "sync-zh", kind: "github-sync", status: "succeeded", percent: 100,
      phase: "done", current: 1, total: 1, etaText: null,
      result: { written: [], failures: {
        portfolio: "No dossier or README found on branch 'feature/$&-dossier'; saved sources were preserved",
        other: "Unexpected provider detail 123",
      }, warnings: ["GitHub rate limit hit; cached docs were preserved. Set GITHUB_TOKEN to raise the limit."] } });
    render(<GithubSyncReport />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("分支“feature/$&-dossier”上未找到项目档案或 README");
    expect(alert).toHaveTextContent("GitHub 请求已达限额");
    expect(alert).toHaveTextContent("Unexpected provider detail 123");
  });

  it("keeps a cancelled status visible when the sync also has warnings", () => {
    useRunStore.getState().upsert({ runId: "sync-cancelled", kind: "github-sync", status: "cancelled", percent: 50,
      phase: "cancelled", current: 1, total: 2, etaText: null,
      result: { written: [], warnings: ["A warning"] } });
    render(<GithubSyncReport />);
    expect(screen.getByRole("alert")).toHaveTextContent("GitHub sync cancelled");
    expect(screen.getByRole("alert")).toHaveTextContent("A warning");
  });
});
