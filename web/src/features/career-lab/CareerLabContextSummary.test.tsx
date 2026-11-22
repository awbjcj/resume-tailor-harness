import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { changeLanguage } from "@/i18n";
import { CareerLabContextSummary } from "./CareerLabContextSummary";

it("removes a job and its dependent resume without dropping other references", async () => {
  const change = vi.fn();
  render(<CareerLabContextSummary context={{ jobId: 4, resumeVersionId: 5, profileSnapshot: "current", offerApplicationIds: [8] }} onChange={change} />);
  await userEvent.click(screen.getByRole("button", { name: "Remove Job #4" }));
  expect(change).toHaveBeenCalledWith({ jobId: undefined, resumeVersionId: undefined, profileSnapshot: "current", offerApplicationIds: [8] });
});

it("localizes reference labels and their removal controls", async () => {
  await changeLanguage("zh-CN");
  const change = vi.fn();
  render(<CareerLabContextSummary context={{ jobId: 4, resumeVersionId: 5, offerApplicationIds: [8] }} onChange={change} />);
  expect(screen.getByRole("button", { name: "移除 职位 #4" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "移除 简历 #5" })).toBeInTheDocument();
  expect(screen.getByText("1 项录用通知参考")).toBeInTheDocument();
});
