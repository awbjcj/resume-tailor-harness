import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { CareerLabContextSummary } from "./CareerLabContextSummary";

it("removes a job and its dependent resume without dropping other references", async () => {
  const change = vi.fn();
  render(<CareerLabContextSummary context={{ jobId: 4, resumeVersionId: 5, profileSnapshot: "current", offerApplicationIds: [8] }} onChange={change} />);
  await userEvent.click(screen.getByRole("button", { name: "Remove Job #4" }));
  expect(change).toHaveBeenCalledWith({ jobId: undefined, resumeVersionId: undefined, profileSnapshot: "current", offerApplicationIds: [8] });
});
