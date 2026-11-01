import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";

const mocks = vi.hoisted(() => ({
  sources: [
    { id: "r1", filename: "resume.pdf", mode: "literal", primary: true,
      anchor: null, addedAt: "2026-07-03", fragmentStatus: "cached", origin: "upload" },
    { id: "d1", filename: "deck.pptx", mode: "synthesis", primary: false,
      anchor: null, addedAt: "2026-07-03", fragmentStatus: "missing", origin: "upload" },
    { id: "n1", filename: "notes.md", mode: "literal", primary: false,
      anchor: null, addedAt: "2026-07-03", fragmentStatus: "cached", origin: "upload" },
    { id: "g1", filename: "github--repo.md", mode: "project", primary: false,
      anchor: null, addedAt: "2026-07-03", fragmentStatus: "cached", origin: "github",
      repoUrl: "https://github.com/ada/repo", githubBranch: "dev" },
    { id: "p1", filename: "portfolio-dossier.md", mode: "project", primary: false,
      anchor: null, addedAt: "2026-07-03", fragmentStatus: "cached", origin: "upload" },
  ],
  skeleton: [{ id: "exp1", kind: "experience", label: "Acme: Engineer" }],
  patch: vi.fn(),
  remove: vi.fn(),
  uploadAll: vi.fn(),
  replace: vi.fn(),
  addNote: vi.fn(),
  addUrl: vi.fn(),
  syncGithub: vi.fn(),
  exclusions: [] as string[],
  restore: vi.fn(),
  download: vi.fn(),
}));

vi.mock("./use-sources", () => ({
  useSources: () => ({ data: mocks.sources, isLoading: false }),
  useSkeleton: () => ({ data: mocks.skeleton }),
  useUploadSources: () => ({ uploadAll: mocks.uploadAll }),
  usePatchSource: () => ({ mutate: mocks.patch, isPending: false }),
  useDeleteSource: () => ({ mutate: mocks.remove, isPending: false }),
  useReplaceSource: () => ({ mutate: mocks.replace, isPending: false }),
  useAddNote: () => ({ mutate: mocks.addNote, isPending: false }),
  useAddUrl: () => ({ mutate: mocks.addUrl, isPending: false }),
  useSyncGithub: () => ({ mutate: mocks.syncGithub, isPending: false }),
  useGithubExclusions: () => ({ data: mocks.exclusions }),
  useRestoreGithubSources: () => ({ mutate: mocks.restore, isPending: false }),
  useDownloadSource: () => ({ mutate: mocks.download, isPending: false }),
}));

import { SourceManager } from "./SourceManager";

describe("SourceManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.exclusions = [];
  });
  afterEach(async () => {
    await changeLanguage("en");
  });
  it("lists sources with mode and primary markers", () => {
    render(<SourceManager />);
    expect(screen.getByText("resume.pdf")).toBeInTheDocument();
    expect(screen.getByText("deck.pptx")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: /resume\.pdf/i })).toBeInTheDocument();
  });

  it("shows an unbuilt source as needing a build instead of missing", () => {
    render(<SourceManager />);
    const row = screen.getByRole("article", { name: /deck\.pptx/i });
    expect(row).toHaveTextContent("Needs build");
    expect(row).not.toHaveTextContent(/missing/i);
  });

  it("identifies a missing file separately and keeps replacement available", () => {
    const source = mocks.sources[1] as typeof mocks.sources[number] & { fileExists?: boolean };
    source.fileExists = false;
    try {
      render(<SourceManager />);
      const row = screen.getByRole("article", { name: /deck\.pptx/i });
      expect(row).toHaveTextContent("File missing");
      expect(screen.getByRole("button", { name: "Download deck.pptx" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Replace deck.pptx" })).toBeEnabled();
    } finally {
      delete source.fileExists;
    }
  });

  it("offers replacement and removal for GitHub sources and uploaded dossiers", () => {
    render(<SourceManager />);
    for (const name of ["github--repo.md", "portfolio-dossier.md", "deck.pptx"]) {
      expect(screen.getByRole("button", { name: `Replace ${name}` })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: `Remove ${name}` })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Remove resume.pdf" })).toBeInTheDocument();
  });

  it("downloads a source and can restore removed GitHub sources", async () => {
    mocks.exclusions = ["github--removed.md"];
    render(<SourceManager />);
    await userEvent.click(screen.getByRole("button", { name: "Download portfolio-dossier.md" }));
    expect(mocks.download).toHaveBeenCalledWith(mocks.sources[4]);
    await userEvent.click(screen.getByRole("button", { name: "Restore removed GitHub sources" }));
    expect(mocks.restore).toHaveBeenCalledTimes(1);
  });

  it("auto-detects uploaded dossiers instead of forcing literal extraction", async () => {
    const { container } = render(<SourceManager />);
    const input = container.querySelector("input[type=file]") as HTMLInputElement;
    const file = new File(["---\nrepo_url: https://github.com/me/project\n---"], "dossier.md");
    await userEvent.upload(input, file);
    expect(mocks.uploadAll).toHaveBeenCalledWith([file], undefined, null);
  });

  it("gives native mode options explicit theme colors", () => {
    render(<SourceManager />);
    const options = screen.getByLabelText(/mode for deck.pptx/i).querySelectorAll("option");
    expect(options).not.toHaveLength(0);
    options.forEach((option) => {
      expect(option).toHaveClass("bg-popover", "text-popover-foreground");
    });
  });

  it("localizes protocol mode and fragment-status display values in Chinese", async () => {
    await changeLanguage("zh-CN");
    render(<SourceManager />);

    const mode = screen.getAllByRole("combobox")
      .find((element) => (element as HTMLSelectElement).value === "synthesis") as HTMLSelectElement;
    expect(mode.selectedOptions[0]?.textContent).toBe("提炼并核验");
    expect(screen.getAllByText("已就绪")).not.toHaveLength(0);
    expect(screen.queryByText("synthesis")).not.toBeInTheDocument();
  });

  it("changes a source's anchor through the skeleton dropdown", async () => {
    render(<SourceManager />);
    const anchorSelect = screen.getByLabelText(/anchor for deck.pptx/i);
    await userEvent.selectOptions(anchorSelect, "exp1");
    expect(mocks.patch).toHaveBeenCalledWith({ id: "d1", anchor: "exp1" });
  });

  it("uploads with the selected mode and anchor", async () => {
    const { container } = render(<SourceManager />);
    await userEvent.selectOptions(screen.getByLabelText(/new source mode/i), "synthesis");
    await userEvent.selectOptions(screen.getByLabelText(/new source anchor/i), "exp1");

    const input = container.querySelector("input[type=file]") as HTMLInputElement;
    const file = new File(["deck"], "deck.md", { type: "text/markdown" });
    await userEvent.upload(input, file);

    expect(mocks.uploadAll).toHaveBeenCalledWith([file], "synthesis", "exp1");
  });

  it("promotes a literal source to primary", async () => {
    render(<SourceManager />);
    await userEvent.click(screen.getByRole("button", { name: /make notes.md primary/i }));
    expect(mocks.patch).toHaveBeenCalledWith({ id: "n1", primary: true });
  });

  it("deletes a source", async () => {
    render(<SourceManager />);
    await userEvent.click(screen.getByRole("button", { name: /remove deck.pptx/i }));
    expect(mocks.remove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Remove source" }));
    expect(mocks.remove).toHaveBeenCalledWith("d1", expect.objectContaining({ onSuccess: expect.any(Function) }));
  });

  it("replaces the primary resume's file", async () => {
    const { container } = render(<SourceManager />);
    await userEvent.click(screen.getByRole("button", { name: /replace resume\.pdf/i }));

    const inputs = container.querySelectorAll("input[type=file]");
    const replaceInput = inputs[inputs.length - 1] as HTMLInputElement;
    const file = new File(["resume v2"], "resume-v2.pdf", { type: "application/pdf" });
    await userEvent.upload(replaceInput, file);

    expect(mocks.replace).toHaveBeenCalledWith({ oldId: "r1", file });
  });

  it("badges github sources and keeps project mode read-only", () => {
    render(<SourceManager />);
    const row = screen.getByRole("article", { name: /github--repo\.md/i });
    expect(row).toHaveTextContent("GitHub");
    expect(row).toHaveTextContent("ada/repo");
    expect(row).toHaveTextContent("dev");
    expect(screen.queryByLabelText(/mode for github--repo\.md/i)).not.toBeInTheDocument();

    const dossier = screen.getByRole("article", { name: /portfolio-dossier\.md/i });
    expect(dossier).not.toHaveTextContent("GitHub");
    expect(screen.getByRole("button", { name: /remove github--repo\.md/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /remove portfolio-dossier\.md/i })).toBeInTheDocument();
  });

  it("submits note and URL intake through labelled dialogs", async () => {
    const user = userEvent.setup();
    render(<SourceManager />);

    await user.click(screen.getByRole("button", { name: /add note/i }));
    await user.type(screen.getByLabelText("Note title"), "On-call");
    await user.type(screen.getByLabelText("Note text"), "Led the rotation.");
    await user.click(screen.getByRole("button", { name: /save note/i }));
    expect(mocks.addNote).toHaveBeenCalledWith(
      { title: "On-call", text: "Led the rotation." },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    act(() => mocks.addNote.mock.calls[0][1].onSuccess());

    await waitFor(() => expect(screen.getByRole("button", { name: /add url/i })).toBeVisible());
    await user.click(screen.getByRole("button", { name: /add url/i }));
    await user.type(screen.getByLabelText("Public URL"), "https://example.com/work");
    await user.click(screen.getByRole("button", { name: /ingest page/i }));
    expect(mocks.addUrl).toHaveBeenCalledWith(
      { url: "https://example.com/work" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

});
