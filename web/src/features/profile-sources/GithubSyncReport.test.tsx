import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useRunStore } from "@/lib/runs/store";
import { GithubSyncReport } from "./GithubSyncReport";

describe("GitHub sync feedback", () => {
  beforeEach(() => useRunStore.setState({ runs: {} }));
  it("makes partial sync failures and recovery visible and retains the report", () => {
    useRunStore.getState().upsert({ runId: "sync", kind: "github-sync", status: "succeeded", percent: 100,
      phase: "done", current: 1, total: 1, etaText: null,
      result: { written: [], failures: { "portfolio": "Branch feature/dossier was not found" }, warnings: [] } });
    render(<GithubSyncReport />);
    expect(screen.getByRole("alert")).toHaveTextContent("Some GitHub sources could not sync");
    expect(screen.getByRole("alert")).toHaveTextContent("Saved copies are kept");
    expect(screen.getByRole("alert")).toHaveTextContent("feature/dossier");
    act(() => useRunStore.getState().remove("sync"));
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
