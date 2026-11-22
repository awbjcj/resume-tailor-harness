import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { ActionQueue, QUEUE_CARDS } from "./ActionQueue";
import { SUMMARY } from "./fixtures";

const renderQueue = (summary = SUMMARY) =>
  render(
    <MemoryRouter>
      <ActionQueue summary={summary} />
    </MemoryRouter>,
  );

describe("ActionQueue", () => {
  it("includes review and render work alongside the existing queues", () => {
    renderQueue();
    expect(QUEUE_CARDS.map((c) => c.key)).toEqual([
      "triage",
      "approve",
      "tailor",
      "apply",
      "review",
      "render",
    ]);
    expect(screen.getByRole("link", { name: /triage 2/i })).toHaveAttribute(
      "href",
      "/triage",
    );
    expect(screen.getByRole("link", { name: /approve 4/i })).toHaveAttribute(
      "href",
      "/shortlist",
    );
    expect(screen.getByRole("link", { name: /tailor a resume for 1 job/i })).toHaveAttribute(
      "href",
      "/pipeline?stage=approved",
    );
    expect(screen.getByRole("link", { name: /apply: prepare 1 application/i })).toHaveAttribute(
      "href",
      "/pipeline?stage=rendered",
    );
  });

  it("keeps zero-count cards visible", () => {
    renderQueue({
      ...SUMMARY,
      queues: { triage: 0, approve: 0, tailor: 0, apply: 0 },
    });
    expect(screen.getAllByRole("link")).toHaveLength(6);
  });

  it("uses complete localized names for queue links when the language changes", async () => {
    renderQueue({ ...SUMMARY, queues: { triage: 2, approve: 1, tailor: 1, apply: 1 } });
    expect(screen.getByRole("link", { name: "Triage 2 jobs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Approve 1 shortlisted job" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tailor a resume for 1 job" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Render PDFs for 0 jobs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Apply: prepare 1 application" })).toBeInTheDocument();

    await act(async () => { await changeLanguage("zh-CN"); });
    expect(screen.getByRole("link", { name: "初筛 2 个职位" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "批准 1 个候选职位" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "为 1 个职位定制简历" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "为 0 个职位生成 PDF" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "准备 1 个职位的申请" })).toBeInTheDocument();

    await act(async () => { await changeLanguage("en"); });
    expect(screen.getByRole("link", { name: "Triage 2 jobs" })).toBeInTheDocument();
  });

  it("opens the exact pending Job and tab when a continuation is available", () => {
    renderQueue({ ...SUMMARY, queueTargets: { render: { jobId: 17, kind: "render", href: "/pipeline?job=17&tab=resumes", resumeVersionId: 9 } } });
    expect(screen.getByRole("link", { name: /render pdfs for 0 jobs/i })).toHaveAttribute("href", "/pipeline?job=17&tab=resumes");
  });
});
