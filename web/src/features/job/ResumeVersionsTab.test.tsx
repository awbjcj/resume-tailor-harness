import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ launch: vi.fn(), api: { DELETE: vi.fn(), GET: vi.fn(), POST: vi.fn() } }));

vi.mock("@/features/runs/use-launch-run", () => ({
  useLaunchRun: () => ({ launch: mocks.launch }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  api: mocks.api,
  openDownload: vi.fn(),
}));

import { useRunStore } from "@/lib/runs/store";
import { changeLanguage } from "@/i18n";
import type { components } from "@/lib/api/schema";
import { ResumeVersionsTab } from "./ResumeVersionsTab";

type Version = components["schemas"]["ResumeVersionOut"];

function wrap(ui: ReactNode, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(ui, {
    wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  });
}

function version(id: number, round: number, overrides: Partial<Version> = {}): Version {
  return {
    id,
    jobId: 3,
    round,
    origin: "tailor",
    reviewScore: 80,
    factCheckPassed: true,
    pdfPath: null,
    critiqueJson: null,
    createdAt: "2026-08-11T00:00:00Z",
    failedGates: [],
    hasEvidencePortfolio: false,
    revisionUnknown: false,
    ...overrides,
  };
}

describe("ResumeVersionsTab", () => {
  beforeEach(() => {
    useRunStore.setState({ runs: {} });
    mocks.launch.mockReset();
    mocks.api.DELETE.mockReset().mockResolvedValue({ data: {} });
    mocks.api.GET.mockReset().mockResolvedValue({ data: [
      { id: "classic", title: "Classic", description: "Traditional serif", kind: "bundled" },
      { id: "modern", title: "Modern", description: "Clean sans serif", kind: "bundled" },
    ] });
    mocks.api.POST.mockReset().mockResolvedValue({ data: { deleted: 2 } });
  });

  it("lists stable version numbers newest first even when review rounds repeat", () => {
    wrap(<ResumeVersionsTab jobId={3} versions={[version(2, 1), version(9, 1)]} appliedVersionId={null} />);

    expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Version 9", "Version 2"]);
    expect(screen.getAllByText("Review round 1")).toHaveLength(2);
  });

  it("hides the cleanup bar when nothing is deletable", () => {
    // A single applied version: there is no cleanup to offer.
    wrap(
      <ResumeVersionsTab jobId={3} versions={[version(1, 0)]} appliedVersionId={1} />,
    );

    expect(screen.queryByText("Select all")).not.toBeInTheDocument();
  });

  it("cannot select or delete the applied version", () => {
    wrap(
      <ResumeVersionsTab
        jobId={3}
        versions={[version(1, 0), version(2, 1)]}
        appliedVersionId={1}
      />,
    );

    // Base UI's Checkbox is a <span role="checkbox">, not a native input, so
    // its disabled state is aria-disabled rather than the DOM `disabled` prop.
    expect(screen.getByLabelText("Select version 1 for deletion")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByLabelText("Delete version 1")).toBeDisabled();
    expect(
      screen.getByLabelText("Select version 2 for deletion"),
    ).not.toHaveAttribute("aria-disabled", "true");
  });

  it("select-all skips the applied version", async () => {
    const user = userEvent.setup();
    wrap(
      <ResumeVersionsTab
        jobId={3}
        versions={[version(1, 0), version(2, 1), version(3, 2)]}
        appliedVersionId={1}
      />,
    );

    await user.click(screen.getByLabelText("Select all deletable versions"));

    expect(screen.getByText("2 selected")).toBeInTheDocument();
  });

  it("requires a fresh delete selection after a version is applied and cleared", async () => {
    const user = userEvent.setup();
    const versions = [version(1, 0), version(2, 1)];
    const { rerender } = wrap(<ResumeVersionsTab jobId={3} versions={versions} appliedVersionId={null} />);
    const selection = screen.getByRole("checkbox", { name: "Select version 1 for deletion" });
    await user.click(selection);
    expect(selection).toBeChecked();

    rerender(<ResumeVersionsTab jobId={3} versions={versions} appliedVersionId={1} />);
    expect(selection).not.toBeChecked();
    rerender(<ResumeVersionsTab jobId={3} versions={versions} appliedVersionId={null} />);

    expect(selection).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Delete selected" })).toBeDisabled();
  });

  it("sends one bulk request for a multi-row delete", async () => {
    const user = userEvent.setup();
    wrap(
      <ResumeVersionsTab
        jobId={3}
        versions={[version(1, 0), version(2, 1)]}
        appliedVersionId={null}
      />,
    );

    await user.click(screen.getByLabelText("Select all deletable versions"));
    await user.click(screen.getByRole("button", { name: /Delete 2 selected/ }));
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));

    expect(mocks.api.POST).toHaveBeenCalledWith(
      "/api/resume-versions/bulk-delete",
      { body: { ids: [1, 2] } },
    );
  });

  it("sends the single-item endpoint when one row is deleted", async () => {
    const user = userEvent.setup();
    wrap(
      <ResumeVersionsTab
        jobId={3}
        versions={[version(1, 0), version(2, 1)]}
        appliedVersionId={null}
      />,
    );

    await user.click(screen.getByLabelText("Delete version 1"));
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));

    expect(mocks.api.DELETE).toHaveBeenCalledWith(
      "/api/resume-versions/{version_id}",
      { params: { path: { version_id: 1 } } },
    );
    expect(mocks.api.POST).not.toHaveBeenCalled();
  });

  it("clears the chosen version through the labeled action", async () => {
    const user = userEvent.setup();
    wrap(
      <ResumeVersionsTab jobId={3} versions={[version(1, 0)]} appliedVersionId={1} />,
    );

    await user.click(screen.getByRole("button", { name: "Clear selection" }));

    expect(mocks.api.DELETE).toHaveBeenCalledWith(
      "/api/jobs/{job_id}/select-resume",
      { params: { path: { job_id: 3 } } },
    );
  });

  it("updates the version and closes the style dialog while boards refresh", async () => {
    const user = userEvent.setup();
    const client = new QueryClient();
    const current = version(9, 1, { pdfAvailable: true, pdfTemplateId: "classic" });
    const updated = { ...current, pdfTemplateId: "modern" };
    const sibling = version(8, 1);
    const job = { application: { resumeVersionId: 9 }, resumeVersions: [current, sibling] };
    client.setQueryData(["job", 3], job);
    const boardRefresh = new Promise<void>(() => {});
    const invalidate = vi.spyOn(client, "invalidateQueries").mockImplementation(({ queryKey } = {}) =>
      queryKey?.[0] === "pipeline" ? boardRefresh : Promise.resolve(),
    );
    mocks.api.POST.mockResolvedValue({ data: updated });
    wrap(<ResumeVersionsTab jobId={3} versions={[current, sibling]} appliedVersionId={9} />, client);

    await user.click(screen.getByRole("button", { name: "Change style" }));
    const dialog = await screen.findByRole("dialog", { name: "Render version 9" });
    expect(within(dialog).getByText("This replaces the PDF selected for your application.")).toBeVisible();
    await within(dialog).findByRole("option", { name: "Modern" });
    const styles = within(dialog).getByLabelText("Resume style");
    expect(styles).toHaveValue("classic");
    await user.selectOptions(styles, "modern");
    await user.click(within(dialog).getByRole("button", { name: "Replace PDF" }));

    expect(mocks.api.POST).toHaveBeenCalledWith("/api/resume-versions/{version_id}/render", {
      params: { path: { version_id: 9 } },
      body: { templateId: "modern" },
    });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Render version 9" })).not.toBeInTheDocument());
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["pipeline"] });
    expect(client.getQueryData(["job", 3])).toEqual({ ...job, resumeVersions: [updated, sibling] });
  });

  it("requires an explicit choice before replacing a PDF whose saved style was removed", async () => {
    const user = userEvent.setup();
    wrap(<ResumeVersionsTab jobId={3} versions={[version(9, 1, { pdfAvailable: true, pdfTemplateId: "custom:missing" })]} appliedVersionId={9} />);

    await user.click(screen.getByRole("button", { name: "Change style" }));
    const dialog = await screen.findByRole("dialog", { name: "Render version 9" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Choose another style");
    const styles = within(dialog).getByRole("combobox", { name: "Resume style" });
    const replace = within(dialog).getByRole("button", { name: "Replace PDF" });
    expect(styles).toHaveValue("custom:missing");
    expect(replace).toBeDisabled();
    expect(mocks.api.POST).not.toHaveBeenCalled();

    await user.selectOptions(styles, "");
    await user.click(replace);
    expect(mocks.api.POST).toHaveBeenCalledWith("/api/resume-versions/{version_id}/render", {
      params: { path: { version_id: 9 } },
    });
  });

  it("shows a failed fit in the style picker and keeps the PDF actions available", async () => {
    const user = userEvent.setup();
    mocks.api.POST.mockResolvedValue({ error: { error: { code: "resume_page_overflow", message: "too long" } } });
    wrap(<ResumeVersionsTab jobId={3} versions={[version(9, 1, { pdfAvailable: true })]} appliedVersionId={null} />);

    await user.click(screen.getByRole("button", { name: "Change style" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Replace PDF" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("could not fit the current page limit");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("button", { name: "Preview" })).toBeEnabled();
  });

  it("localizes resume identity, style choices, and deletion controls", async () => {
    await changeLanguage("zh-CN");
    const user = userEvent.setup();
    wrap(<ResumeVersionsTab jobId={3} versions={[version(9, 1, { pdfAvailable: true, pdfTemplateId: "classic" })]} appliedVersionId={null} />);

    expect(screen.getByRole("heading", { name: "第 9 版" })).toBeInTheDocument();
    const deleteButton = screen.getByRole("button", { name: "删除第 9 版" });
    expect(deleteButton).toBeEnabled();
    expect(deleteButton).toHaveTextContent("删除");
    await user.click(screen.getByRole("button", { name: "更换样式" }));
    const dialog = await screen.findByRole("dialog", { name: "为第 9 版生成 PDF" });
    expect(await within(dialog).findByRole("option", { name: "经典" })).toBeInTheDocument();
  });
});
