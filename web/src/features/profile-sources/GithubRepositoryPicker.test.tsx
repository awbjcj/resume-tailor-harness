import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { GithubRepositoryPicker } from "./GithubRepositoryPicker";

const repository = { owner: "ada", name: "engine", fullName: "ada/engine", defaultBranch: "main", selectedBranch: null, included: true };

describe("GitHub repository branches", () => {
  it("loads real branch options and preserves slash names in the saved repository mapping", async () => {
    server.use(
      http.get("/api/profile/github/repositories", () => HttpResponse.json([repository])),
      http.get("/api/profile/github/repositories/ada/engine/branches", () => HttpResponse.json(["main", "dev", "feature/dossier"])),
    );
    const change = vi.fn();
    render(<GithubRepositoryPicker username="ada" branches={{ "ada/other": "release" }} settingsKey="saved" disabled={false} onChange={change} />, { wrapper: withQueryClient });
    await userEvent.click(screen.getByRole("button", { name: "Choose repository branches" }));
    const select = await screen.findByLabelText("Branch for ada/engine");
    await userEvent.click(select);
    await screen.findByRole("option", { name: "feature/dossier" });
    await userEvent.click(screen.getByRole("option", { name: "feature/dossier" }));
    expect(change).toHaveBeenCalledWith({ "ada/other": "release", "ada/engine": "feature/dossier" });
  });

  it("keeps a configured branch visible when loading branches fails and offers retry", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/profile/github/repositories", () => HttpResponse.json([repository])),
      http.get("/api/profile/github/repositories/ada/engine/branches", () => {
        attempts += 1;
        return attempts === 1 ? HttpResponse.json({ error: { message: "unavailable" } }, { status: 422 }) : HttpResponse.json(["dev"]);
      }),
    );
    render(<GithubRepositoryPicker username="ada" branches={{ "ada/engine": "dev" }} settingsKey="saved" disabled={false} onChange={vi.fn()} />, { wrapper: withQueryClient });
    await userEvent.click(screen.getByRole("button", { name: "Choose repository branches" }));
    const select = await screen.findByLabelText("Branch for ada/engine");
    expect(select).toHaveTextContent("dev");
    await userEvent.click(select);
    await screen.findByRole("alert");
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Retry branches" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(select).toHaveTextContent("dev");
  });
});
