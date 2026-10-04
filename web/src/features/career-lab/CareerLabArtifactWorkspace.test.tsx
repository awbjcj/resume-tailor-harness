import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { CareerLabArtifactWorkspace } from "./CareerLabArtifactWorkspace";
import type { CareerLabSession } from "./use-career-lab";

const turns = [
  { turnId: "first", role: "assistant", text: "## Experience\nOriginal evidence", artifact: { title: "First draft", summary: "Summary", artifactType: "career_plan" } },
  { turnId: "second", role: "assistant", text: "## Next steps\nUpdated plan", artifact: { title: "Second draft", summary: "Summary", artifactType: "career_plan" } },
] as CareerLabSession["turns"];

it("shows the latest draft and prepares section feedback against that exact turn", async () => {
  const revise = vi.fn();
  render(<CareerLabArtifactWorkspace turns={turns!} selectedId={null} onSelect={vi.fn()} onRevise={revise} busy={false} />);
  expect(screen.getByLabelText("Draft content")).toHaveTextContent("Updated plan");
  await userEvent.selectOptions(screen.getByLabelText("Revision scope"), "Next steps");
  await userEvent.type(screen.getByLabelText("Feedback"), "Make the actions more specific");
  await userEvent.click(screen.getByRole("button", { name: "Prepare revision request" }));
  expect(revise).toHaveBeenCalledWith("second", expect.stringContaining('section "Next steps"'));
  expect(revise.mock.calls[0][1]).toContain("Make the actions more specific");
});

it("keeps a selected historical draft visible while a new response streams", () => {
  render(<CareerLabArtifactWorkspace turns={turns!} selectedId="first" onSelect={vi.fn()} onRevise={vi.fn()} busy liveText="New response" />);
  expect(screen.getByLabelText("Draft content")).toHaveTextContent("Original evidence");
  expect(screen.getByText("Response in progress")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Prepare revision request" })).toBeDisabled();
});

it.each(["external selection", "latest draft arrival"])("resets revision scope and feedback on %s", async (change) => {
  const revise = vi.fn();
  const props = { onSelect: vi.fn(), onRevise: revise, busy: false };
  const { rerender } = render(<CareerLabArtifactWorkspace {...props} turns={turns!.slice(0, 1)} selectedId={change === "external selection" ? "first" : null} />);
  await userEvent.selectOptions(screen.getByLabelText("Revision scope"), "Experience");
  await userEvent.type(screen.getByLabelText("Feedback"), "Old draft feedback");
  rerender(<CareerLabArtifactWorkspace {...props} turns={turns!} selectedId={change === "external selection" ? "second" : null} />);
  expect(screen.getByLabelText("Revision scope")).toHaveValue("");
  expect(screen.getByLabelText("Feedback")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Prepare revision request" })).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Feedback"), "Revise this new draft");
  await userEvent.click(screen.getByRole("button", { name: "Prepare revision request" }));
  expect(revise).toHaveBeenCalledWith("second", expect.stringContaining("Revise this new draft"));
  expect(revise.mock.calls[0][1]).not.toContain("Experience");
});
