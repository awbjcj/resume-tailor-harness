import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { withQueryClient } from "@/test/utils";
import { ProfileWorkspace } from "./ProfileWorkspace";

const mocks = vi.hoisted(() => ({
  launch: vi.fn().mockResolvedValue(true),
  save: vi.fn(),
  config: {
    githubUsername: null as string | null,
    githubRepoAllow: [] as string[],
    githubRepoDeny: [] as string[],
    githubRepoLimit: 20,
  },
}));

vi.mock("@/features/profile-sources/BuildReportPanel", () => ({
  BuildReportPanel: () => <div data-testid="build-report" />,
}));

vi.mock("@/features/profile-sources/SourceManager", () => ({
  SourceManager: () => <div data-testid="source-manager" />,
}));

vi.mock("@/features/coach/use-coach", () => ({
  useCoachSessions: () => ({ data: { sessions: [] } }),
}));

vi.mock("@/features/settings/SkillGroupsPanel", () => ({
  SkillGroupsPanel: () => <div data-testid="skill-groups" />,
}));

vi.mock("@/features/runs/use-active-run", () => ({
  useActiveRun: () => null,
}));

vi.mock("@/features/runs/use-launch-run", () => ({
  launchers: { profileBuild: vi.fn() },
  useLaunchRun: () => ({ launch: mocks.launch }),
}));

vi.mock("@/features/settings/use-config", () => ({
  useConfig: () => ({
    data: mocks.config,
  }),
  useSaveConfig: () => ({ isPending: false, mutate: mocks.save }),
}));

vi.mock("@/features/settings/use-setup-status", () => ({
  useSetupStatus: () => ({ data: { profile: { factsBuiltAt: null } } }),
}));

describe("ProfileWorkspace", () => {
  beforeEach(() => {
    mocks.config = {
      githubUsername: null,
      githubRepoAllow: [],
      githubRepoDeny: [],
      githubRepoLimit: 20,
    };
    mocks.save.mockClear();
  });
  function renderWorkspace(initialEntry = "/profile") {
    return render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <ProfileWorkspace />
      </MemoryRouter>,
      { wrapper: withQueryClient },
    );
  }

  it("keeps the coach hero visible and refreshes queries after a profile rebuild", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    // coach is a persistent hero action, not tucked in a tab
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: /open coach/i })).toHaveAttribute(
      "href",
      "/coach",
    );

    await user.click(screen.getByRole("button", { name: /build profile/i }));

    await waitFor(() =>
      expect(mocks.launch).toHaveBeenCalledWith(
        "profile-build",
        expect.any(Function),
        [
          "setup-status",
          "profile-sources",
          "profile-skeleton",
          "profile-matrix",
          "profile-skills",
          "skill-cleanup",
          "suppressed-skills",
          "match-gap",
          "job",
          "triage",
          "shortlist",
          "pipeline",
        ],
      ),
    );
  });

  it("edits repo harvest controls on Documents and mounts grouped skills on Skills", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    await user.click(screen.getByText("Import preferences"));
    await user.type(
      screen.getByLabelText(/always include repositories/i),
      "important, fork",
    );
    await user.type(screen.getByLabelText(/exclude repositories/i), "noise");
    await user.clear(screen.getByLabelText(/repository limit/i));
    await user.type(screen.getByLabelText(/repository limit/i), "5");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(mocks.save).toHaveBeenCalledWith(
      expect.objectContaining({
        githubRepoAllow: ["important", "fork"],
        githubRepoDeny: ["noise"],
        githubRepoLimit: 5,
      }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );

    // Skills live behind their own tab — no longer stacked on one page
    expect(screen.queryByTestId("skill-groups")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /skills/i }));
    expect(await screen.findByTestId("skill-groups")).toBeInTheDocument();
  });

  it("opens the skills tab from a dashboard deep link", async () => {
    renderWorkspace("/profile?tab=skills");

    expect(await screen.findByTestId("skill-groups")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /skills/i })).toHaveAttribute(
      "data-active",
    );
  });

  it("blocks sync and build until GitHub changes have been saved", async () => {
    renderWorkspace();
    await userEvent.type(screen.getByLabelText("GitHub username"), "ada");
    expect(
      screen.getByRole("button", { name: "Build profile" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Sync GitHub" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Save your GitHub changes",
    );
  });

  it("keeps invalid limits dirty and lets the user discard them", async () => {
    renderWorkspace();
    await userEvent.click(screen.getByText("Import preferences"));
    await userEvent.clear(screen.getByLabelText("Repository limit"));
    expect(
      screen.getByRole("button", { name: "Build profile" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.getByLabelText("Repository limit")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.getByLabelText("Repository limit")).toHaveValue(20);
    expect(screen.getByRole("button", { name: "Build profile" })).toBeEnabled();
  });

  it("preserves visible unsaved inputs when saved config refreshes", async () => {
    const view = renderWorkspace();
    await userEvent.click(screen.getByText("Import preferences"));
    await userEvent.type(
      screen.getByLabelText("Always include repositories"),
      "engine, ",
    );
    mocks.config = { ...mocks.config, githubRepoAllow: ["remote-change"] };
    view.rerender(
      <MemoryRouter>
        <ProfileWorkspace />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText("Always include repositories")).toHaveValue(
      "engine, ",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(mocks.save).toHaveBeenCalledWith(
      expect.objectContaining({ githubRepoAllow: ["engine"] }),
      expect.any(Object),
    );
  });
});
