import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { useRunStore } from "@/lib/runs/store";

import { BuildReportPanel } from "./BuildReportPanel";

describe("BuildReportPanel", () => {
  beforeEach(async () => {
    await changeLanguage("en");
    useRunStore.setState({ runs: {} });
  });

  it("renders nothing without a completed build", () => {
    const { container } = render(<BuildReportPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the running build instead of a previous success and exposes failures", () => {
    useRunStore.setState({ runs: {
      old: { runId: "old", kind: "profile-build", status: "succeeded", updatedAt: 1,
        percent: 100, phase: "done", current: 3, total: 3, etaText: null, result: { projects: 2 } },
      current: { runId: "current", kind: "profile-build", status: "running", updatedAt: 2,
        percent: 25, phase: "Extracting and merging source documents", current: 1, total: 3, etaText: null },
    } });
    const { unmount } = render(<BuildReportPanel />);
    expect(screen.getByRole("progressbar", { name: "Profile build progress" })).toHaveAttribute("aria-valuenow", "25");
    expect(screen.queryByText("Profile ready")).not.toBeInTheDocument();
    unmount();
    useRunStore.setState({ runs: { failure: { runId: "failure", kind: "profile-build", status: "failed", updatedAt: 3,
      percent: 25, phase: "", current: 1, total: 3, etaText: null, error: "Provider unavailable" } } });
    render(<BuildReportPanel />);
    expect(screen.getByRole("alert")).toHaveTextContent("Profile build failed");
    expect(screen.getByRole("alert")).toHaveTextContent("build your profile again");
  });

  it("shows anchors, drops, and warnings from the run result", () => {
    useRunStore.getState().upsert({
      runId: "r1", kind: "profile-build", status: "succeeded",
      percent: 100, phase: "done", current: 3, total: 3, etaText: null,
      result: {
        experiences: 3, projects: 2,
        docStatus: { "resume-1": "cached", "deck-1": "extracted" },
        anchorDecisions: ["deck-1: +2 bullets on Acme/Engineer"],
        verificationDrops: ["deck-1: 'Cut latency 45%' (number '45%' not in source)"],
        warnings: ["skill inference failed: boom"],
      },
    });
    render(<BuildReportPanel />);
    expect(screen.getByText(/deck-1: extracted/)).toBeInTheDocument();
    expect(screen.getByText(/\+2 bullets on Acme\/Engineer/)).toBeInTheDocument();
    expect(screen.getByText(/45%/)).toBeInTheDocument();
    expect(screen.getByText(/skill inference failed/)).toBeInTheDocument();
    act(() => useRunStore.getState().remove("r1"));
    expect(screen.getByText("Profile ready")).toBeInTheDocument();
  });

  it("uses fixed Chinese copy for known build diagnostics while retaining evidence details", async () => {
    await changeLanguage("zh-CN");
    useRunStore.setState({
      runs: {
        build: {
          runId: "build", kind: "profile-build", status: "succeeded", updatedAt: 1,
          percent: 100, phase: "done", current: 3, total: 3, etaText: null,
          result: {
            experiences: 3, projects: 2,
            docStatus: { "resume-1": "failed: parser unavailable" },
            anchorDecisions: ["deck-1: +2 bullets on Acme/Engineer"],
            verificationDrops: ["deck-1: 'Cut latency 45%' (number '45%' not in source)"],
            conflicts: ["summary: 'Current' kept over 'Other' from deck-1"],
            warnings: [
              "skill inference failed: boom",
              "Manual alias 'TS' could not be reattached. Its target skill 'TypeScript' was not found.",
            ],
          },
        },
      },
    });

    render(<BuildReportPanel />);

    expect(screen.getByText("resume-1: 提取失败：parser unavailable")).toBeInTheDocument();
    expect(screen.getByText("deck-1：已将 2 条要点添加到 Acme/Engineer")).toBeInTheDocument();
    expect(screen.getByText("deck-1：已移除 'Cut latency 45%'（来源中未找到数字 '45%'）")).toBeInTheDocument();
    expect(screen.getByText("summary：保留 'Current'，未采用来自 deck-1 的 'Other'")).toBeInTheDocument();
    expect(screen.getByText("技能推断失败：boom")).toBeInTheDocument();
    expect(screen.getByText("无法恢复手动设置的别名“TS”：未找到对应技能“TypeScript”。")).toBeInTheDocument();
  });
});
