import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { withQueryClient } from "@/test/utils";

const state = vi.hoisted(() => ({
  value: {} as Record<string, unknown>,
  suppressed: [] as Array<Record<string, unknown>>,
  cleanup: {
    enabled: true,
    beforeCount: 2,
    afterCount: 2,
    merges: [],
    pruned: [],
  },
  refetch: vi.fn(),
  add: vi.fn(),
  update: vi.fn(),
  move: vi.fn(),
  merge: vi.fn(),
  clean: vi.fn(),
  policy: vi.fn(),
  organize: vi.fn(),
  remove: vi.fn(),
  restore: vi.fn(),
  launch: vi.fn().mockResolvedValue(true),
}));
vi.mock("@/features/profile-skills/use-profile-skills", () => ({
  SKILL_MUTATION_KEY: ["profile-skill-mutation"],
  useAddSkill: () => ({ mutate: state.add, isPending: false }),
  useUpdateSkill: () => ({ mutate: state.update, isPending: false }),
  useMoveSkillGroup: () => ({ mutate: state.move, isPending: false }),
  useMergeProfileSkills: () => ({ mutate: state.merge, isPending: false }),
  useCleanProfileSkills: () => ({ mutate: state.clean, isPending: false }),
  useSkillCleanupPolicy: () => ({ mutate: state.policy, isPending: false }),
  useSkillOrganization: () => ({
    mutate: state.organize,
    isPending: false,
    reset: vi.fn(),
  }),
  useSkillCleanup: () => ({
    data: state.cleanup,
    isPending: false,
    isError: false,
  }),
}));
vi.mock("./use-matrix", () => ({
  useMatrix: () => ({ ...state.value, refetch: state.refetch }),
  useDeleteSkill: () => ({ mutate: state.remove, isPending: false }),
  useRestoreSkill: () => ({ mutate: state.restore, isPending: false }),
  useSuppressedSkills: () => ({ data: state.suppressed }),
}));
vi.mock("@/features/runs/use-active-run", () => ({
  useActiveRun: () => undefined,
}));
vi.mock("@/features/runs/use-launch-run", () => ({
  useLaunchRun: () => ({ launch: state.launch }),
}));

import { SkillGroupsPanel } from "./SkillGroupsPanel";

const groups = [
  { slug: "languages", label: "Languages", category: "technical" },
  { slug: "other", label: "Other", category: "other" },
];
const categories = [
  { slug: "technical", label: "Technical skills" },
  { slug: "other", label: "Other" },
];
const rows = [
  {
    key: "python",
    display: "Python",
    aliases: ["py"],
    category: "hard",
    group: "languages",
    groupSource: "correction",
    inferred: false,
    strength: 3,
  },
  {
    key: "rust",
    display: "Rust",
    aliases: ["rustlang"],
    category: "hard",
    group: null,
    inferred: true,
    strength: 1,
  },
];
function show(disabled = false) {
  return render(<SkillGroupsPanel disabled={disabled} />, {
    wrapper: withQueryClient,
  });
}

describe("SkillGroupsPanel skill library", () => {
  beforeEach(() => {
    localStorage.removeItem("profile-skills-view");
    for (const value of Object.values(state))
      if (typeof value === "function" && "mockClear" in value)
        value.mockClear();
    state.value = {
      isPending: false,
      isError: false,
      data: { generatedAt: "2026-11-01T00:00:00Z", groups, categories, rows },
    };
    state.suppressed = [];
  });
  it("shows loading, retry and profile-first empty states", async () => {
    state.value = { isPending: true };
    const first = show();
    expect(screen.getByLabelText("Loading skill matrix")).toBeInTheDocument();
    first.unmount();
    state.value = {
      isPending: false,
      isError: true,
      error: new Error("offline"),
    };
    const second = show();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(state.refetch).toHaveBeenCalledOnce();
    second.unmount();
    state.value = {
      isPending: false,
      data: { generatedAt: "", groups, rows: [] },
    };
    show();
    expect(screen.getByText("Start with your profile")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Rebuild skills" }),
    ).toBeDisabled();
  });
  it("searches aliases and filters categories and evidence", async () => {
    const user = userEvent.setup();
    show();
    await user.type(
      screen.getByRole("textbox", { name: "Search skills and aliases" }),
      "rustlang",
    );
    expect(screen.getByText("Rust")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Python" }),
    ).not.toBeInTheDocument();
    await user.clear(
      screen.getByRole("textbox", { name: "Search skills and aliases" }),
    );
    await user.click(screen.getByRole("button", { name: /Technical skills/ }));
    expect(
      screen.queryByRole("button", { name: "Rust" }),
    ).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Filter by evidence"),
      "inferred",
    );
    expect(screen.getByText("No matching skills")).toBeInTheDocument();
  });
  it("creates a skill with aliases and a selected group in one mutation", async () => {
    const user = userEvent.setup();
    show();
    await user.click(screen.getByRole("button", { name: "Add skill" }));
    await user.type(screen.getByLabelText("Skill name"), "TypeScript");
    await user.type(screen.getByLabelText("Aliases", { exact: true }), "TS");
    await user.selectOptions(
      screen.getByLabelText("Group", { exact: true }),
      "languages",
    );
    await user.click(screen.getByRole("button", { name: "Add skill" }));
    expect(state.add).toHaveBeenCalledWith(
      {
        name: "TypeScript",
        aliases: ["TS"],
        category: "hard",
        group: "languages",
      },
      expect.any(Object),
    );
  });
  it("edits the skill name, aliases, type and group", async () => {
    const user = userEvent.setup();
    show();
    await user.click(screen.getByRole("button", { name: "Edit Python" }));
    await user.clear(screen.getByLabelText("Skill name"));
    await user.type(screen.getByLabelText("Skill name"), "Python programming");
    await user.selectOptions(screen.getByLabelText("Skill type"), "domain");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(state.update).toHaveBeenCalledWith(
      {
        key: "python",
        name: "Python programming",
        aliases: ["py"],
        category: "domain",
        group: "languages",
      },
      expect.any(Object),
    );
  });
  it("merges selected skills using an explicitly chosen target", async () => {
    const user = userEvent.setup();
    show();
    await user.click(screen.getByRole("checkbox", { name: "Select Python" }));
    expect(
      screen.getByRole("button", { name: "Merge selected" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "Select Rust" }));
    await user.click(screen.getByRole("button", { name: "Merge selected" }));
    await user.selectOptions(screen.getByLabelText("Keep this skill"), "rust");
    await user.click(screen.getByRole("button", { name: "Merge skills" }));
    expect(state.merge).toHaveBeenCalledWith(
      { keys: ["python", "rust"], into: "rust" },
      expect.any(Object),
    );
  });

  it("preserves an unspecified skill type when editing aliases", async () => {
    state.value = {
      isPending: false,
      data: { generatedAt: "2026-11-01", groups, categories, rows: [{ ...rows[0], category: null }] },
    };
    show();
    await userEvent.click(screen.getByRole("button", { name: "Edit Python" }));
    expect(screen.getByLabelText("Skill type")).toHaveValue("unspecified");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(state.update).toHaveBeenCalledWith(expect.objectContaining({ category: null }), expect.any(Object));
  });
  it("creates a user category and exposes group edit/delete controls", async () => {
    const user = userEvent.setup();
    show();
    await user.click(
      screen.getByRole("button", { name: "Groups & categories" }),
    );
    expect(
      screen.getByRole("button", { name: "Edit group Languages" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete group Other" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Add category" }));
    await user.type(
      screen.getByLabelText("Name", { exact: true }),
      "My specialty",
    );
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(state.organize).toHaveBeenCalledWith(
      { kind: "category", label: "My specialty", category: "other" },
      expect.any(Object),
    );
  });
  it("deletes, restores, and changes the automatic cleanup policy", async () => {
    const user = userEvent.setup();
    state.suppressed = [{ token: "kubernetes", display: "Kubernetes" }];
    show();
    await user.click(screen.getByRole("button", { name: "Delete Python" }));
    expect(state.remove).toHaveBeenCalledWith("python");
    await user.click(screen.getByText(/Removed skills \(1\)/));
    await user.click(
      screen.getByRole("button", { name: "Restore Kubernetes" }),
    );
    expect(state.restore).toHaveBeenCalledWith("kubernetes");
    await user.click(
      screen.getByRole("switch", { name: "Keep skills clean automatically" }),
    );
    expect(state.policy).toHaveBeenCalledWith(false);
  });
  it("starts rebuild/reclassification and disables mutations during profile operations", async () => {
    const user = userEvent.setup();
    const view = show();
    await user.click(screen.getByRole("button", { name: "Rebuild skills" }));
    expect(state.launch).toHaveBeenCalledWith(
      "profile-skills-rebuild",
      expect.any(Function),
    );
    await user.click(screen.getByRole("button", { name: "Reclassify" }));
    expect(state.launch).toHaveBeenCalledTimes(2);
    view.rerender(<SkillGroupsPanel disabled />);
    expect(screen.getByRole("button", { name: "Add skill" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Delete Python" }),
    ).toBeDisabled();
  });
  it("shows all skills and empty groups in compact view and remembers the choice", async () => {
    state.value = {
      isPending: false,
      data: {
        generatedAt: "2026-11-01",
        groups,
        categories,
        rows: [
          ...rows,
          ...Array.from({ length: 45 }, (_, i) => ({
            ...rows[0],
            key: `skill-${i}`,
            display: `Skill ${i}`,
          })),
        ],
      },
    };
    const user = userEvent.setup();
    const view = show();
    await user.click(screen.getByRole("button", { name: "Compact" }));
    expect(
      screen.getByRole("button", { name: "Skill 44" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Next skills page" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Category actions for Technical skills",
      }),
    ).toBeInTheDocument();
    expect(localStorage.getItem("profile-skills-view")).toBe("compact");
    view.unmount();
    show();
    expect(screen.getByRole("button", { name: "Compact" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("opens a skill context window and moves it without dragging", async () => {
    const user = userEvent.setup();
    show();
    await user.click(screen.getByRole("button", { name: "Compact" }));
    await user.click(screen.getByRole("button", { name: "Python" }));
    expect(screen.getByRole("dialog", { name: "Python" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Move to group"), "other");
    await user.click(screen.getByRole("button", { name: "Move skill" }));
    expect(state.move).toHaveBeenCalledWith(
      { key: "python", group: "other" },
      expect.any(Object),
    );
  });

  it("uses category context windows to edit the catalog", async () => {
    const user = userEvent.setup();
    show();
    await user.click(screen.getByRole("button", { name: "Compact" }));
    await user.click(
      screen.getByRole("button", {
        name: "Category actions for Technical skills",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Edit category" }));
    await user.clear(screen.getByLabelText("Name", { exact: true }));
    await user.type(
      screen.getByLabelText("Name", { exact: true }),
      "Engineering",
    );
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(state.organize).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "category",
        key: "technical",
        label: "Engineering",
      }),
      expect.any(Object),
    );
  });

  it("adds a skill directly from a group context window", async () => {
    const user = userEvent.setup();
    show();
    await user.click(screen.getByRole("button", { name: "Compact" }));
    await user.click(
      screen.getByRole("button", { name: "Group actions for Languages" }),
    );
    await user.click(
      within(screen.getByRole("dialog", { name: "Languages" })).getByRole(
        "button",
        { name: "Add skill" },
      ),
    );
    expect(
      screen.getByRole("dialog", { name: "Add a skill" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Group", { exact: true })).toHaveValue(
      "languages",
    );
  });
});
