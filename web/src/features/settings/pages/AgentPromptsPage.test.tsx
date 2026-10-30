import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { withQueryClient } from "@/test/utils";
import { AgentPromptsPage } from "./AgentPromptsPage";

const save = vi.fn();
const items = [
  {
    key: "tailor-writer",
    title: "Resume writer",
    stage: "tailoring",
    description: "Writes a targeted resume under the profile fact-lock.",
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
    guidance: null,
    editable: false,
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
  {
    key: "email-writer",
    title: "Email writer",
    stage: "email",
    description: "Drafts fact-grounded job-search emails.",
    instructions: [..."Draft a thoughtful email.", "Additional quality rules."],
    guidance: null,
    editable: true,
  },
];

vi.mock("../use-prompts", () => ({
  usePrompts: () => ({ data: items, isPending: false, isError: false }),
  useSaveGuidance: () => ({ mutate: save, isPending: false }),
}));

describe("AgentPromptsPage", () => {
  beforeEach(() => save.mockClear());
  afterEach(async () => { await changeLanguage("en"); });

  it("groups agents and reveals immutable base instructions", async () => {
    render(<AgentPromptsPage />, { wrapper: withQueryClient });
    expect(screen.getByRole("heading", { name: "Tailoring" })).toBeInTheDocument();
    await userEvent.click(screen.getByText("Resume writer"));
    expect(screen.getByText("Rule one.")).toBeInTheDocument();
  });

  it("localizes built-in labels while showing the original instructions and guidance", async () => {
    await changeLanguage("zh-CN");
    render(<AgentPromptsPage />, { wrapper: withQueryClient });

    expect(screen.getByText("内置指令以原文显示。")).toBeInTheDocument();
    expect(screen.getByText("依据个人资料中的事实撰写针对职位的简历。")).toBeInTheDocument();
    await userEvent.click(screen.getByText("简历写作助手"));
    expect(screen.getByText("Rule one.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /简历写作助手/ })).toHaveValue("");
  });

  it("displays character-split email instructions as readable text", async () => {
    render(<AgentPromptsPage />, { wrapper: withQueryClient });
    await userEvent.click(screen.getByText("Email writer"));

    expect(screen.getByText("Draft a thoughtful email.")).toBeInTheDocument();
    expect(screen.getByText("Additional quality rules.")).toBeInTheDocument();
  });

  it("saves editable guidance and keeps integrity gates read-only", async () => {
    render(<AgentPromptsPage />, { wrapper: withQueryClient });
    await userEvent.click(screen.getByText("Resume writer"));
    await userEvent.type(screen.getByLabelText("Your guidance for Resume writer"), "Punchy verbs.");
    await userEvent.click(screen.getByRole("button", { name: "Save guidance" }));
    expect(save).toHaveBeenCalledWith({
      key: "tailor-writer",
      guidance: "Punchy verbs.",
    });

    await userEvent.click(screen.getByText("Fact-check gate"));
    expect(screen.getByText("Integrity gate (read-only)")).toBeInTheDocument();
    expect(screen.queryByLabelText(/guidance for Fact-check/i)).not.toBeInTheDocument();
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

  it("does not offer a reset control on an integrity gate", async () => {
    const user = userEvent.setup();
    render(<AgentPromptsPage />, { wrapper: withQueryClient });

    await user.click(screen.getByText("Fact-check gate"));
    expect(
      screen.queryByRole("button", { name: /reset this agent/i }),
    ).not.toBeInTheDocument();
  });
});
