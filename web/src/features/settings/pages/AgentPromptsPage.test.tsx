import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { withQueryClient } from "@/test/utils";
import { AgentPromptsPage } from "./AgentPromptsPage";

const save = vi.fn();
const items = [
  {
    key: "tailor-writer",
    title: "Resume writer",
    stage: "tailoring",
    description: "Writes the targeted resume.",
    instructions: ["Rule one.", "Rule two."],
    guidance: null,
    editable: true,
  },
  {
    key: "reviewer-fact-check",
    title: "Fact-check gate",
    stage: "review",
    description: "Hard integrity gate.",
    instructions: ["Verify every claim."],
    guidance: "Check each claim against cited facts.",
    editable: true,
  },
  {
    key: "tailor-reviser",
    title: "Resume reviser",
    stage: "tailoring",
    description: "Revises drafts against reviewer feedback.",
    instructions: ["Revise carefully."],
    guidance: "Existing guidance text.",
    editable: true,
  },
];

vi.mock("../use-prompts", () => ({
  usePrompts: () => ({ data: items, isPending: false, isError: false }),
  useSaveGuidance: () => ({ mutate: save, isPending: false }),
}));

describe("AgentPromptsPage", () => {
  beforeEach(() => save.mockClear());

  it("groups agents and reveals immutable base instructions", async () => {
    render(<AgentPromptsPage />, { wrapper: withQueryClient });
    expect(screen.getByRole("heading", { name: "Tailoring" })).toBeInTheDocument();
    await userEvent.click(screen.getByText("Resume writer"));
    expect(screen.getByText("Rule one.")).toBeInTheDocument();
  });

  it("saves guidance for writers", async () => {
    render(<AgentPromptsPage />, { wrapper: withQueryClient });
    await userEvent.click(screen.getByText("Resume writer"));
    await userEvent.type(screen.getByLabelText("Your guidance for Resume writer"), "Punchy verbs.");
    await userEvent.click(screen.getByRole("button", { name: "Save guidance" }));
    expect(save).toHaveBeenCalledWith({
      key: "tailor-writer",
      guidance: "Punchy verbs.",
    });
  });

  it("saves the fact-check procedure while showing its evidence rules", async () => {
    render(<AgentPromptsPage />, { wrapper: withQueryClient });
    await userEvent.click(screen.getByText("Fact-check gate"));
    expect(screen.getByText("Verify every claim.")).toBeInTheDocument();
    const guidance = screen.getByLabelText("Your guidance for Fact-check gate");
    await userEvent.clear(guidance);
    await userEvent.type(guidance, "Check metrics first.");
    await userEvent.click(screen.getByRole("button", { name: "Save guidance" }));
    expect(save).toHaveBeenLastCalledWith({
      key: "reviewer-fact-check",
      guidance: "Check metrics first.",
    });
  });

  it("resetting one agent clears just its guidance", async () => {
    const user = userEvent.setup();
    render(<AgentPromptsPage />, { wrapper: withQueryClient });

    await user.click(screen.getByText("Resume reviser"));
    await user.click(screen.getByRole("button", { name: /reset this agent/i }));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith({ key: "tailor-reviser", guidance: "" }),
    );
  });

  it("resets the fact-check procedure guidance", async () => {
    const user = userEvent.setup();
    render(<AgentPromptsPage />, { wrapper: withQueryClient });

    await user.click(screen.getByText("Fact-check gate"));
    await user.click(screen.getByRole("button", { name: /reset this agent/i }));
    expect(save).toHaveBeenCalledWith({ key: "reviewer-fact-check", guidance: "" });
  });
});
