import { act, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { withQueryClient } from "@/test/utils";
import { SkillEditorDialog } from "./SkillEditorDialog";

vi.mock("./use-profile-skills", () => ({
  useAddSkill: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateSkill: () => ({ mutate: vi.fn(), isPending: false }),
  useAddSkillAlias: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("skill editor language changes", () => {
  it("updates all type options in an open editor when the interface language changes", async () => {
    render(<SkillEditorDialog groups={[]} onClose={vi.fn()} />, { wrapper: withQueryClient });
    expect(screen.getByRole("option", { name: "Hard skill" })).toBeInTheDocument();
    await act(async () => { await changeLanguage("zh-CN"); });
    const select = screen.getByRole("combobox", { name: "技能类型" });
    expect(within(select).getByRole("option", { name: "硬技能" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "软技能" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "领域知识" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "未确定" })).toBeInTheDocument();
    await act(async () => { await changeLanguage("en"); });
    expect(screen.getByRole("option", { name: "Domain knowledge" })).toBeInTheDocument();
  });
});
