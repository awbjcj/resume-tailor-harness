import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { withQueryClient } from "@/test/utils";
import { RenderingSettingsPage } from "./RenderingSettingsPage";

const save = vi.fn();
const upload = vi.fn();
const remove = vi.fn();

vi.mock("../use-config", () => ({
  useConfig: () => ({ data: { template: "classic", fitOnePage: true } }),
  useSaveConfig: () => ({ mutate: save, isPending: false }),
}));
vi.mock("../use-render-templates", () => ({
  useRenderTemplates: () => ({
    data: [
      { id: "classic", title: "Classic", description: "Bundled", kind: "bundled" },
      { id: "custom:mine", title: "mine", description: "Uploaded", kind: "custom" },
    ],
    isPending: false,
    isError: false,
  }),
  useUploadTemplate: () => ({ mutate: upload, isPending: false, error: null }),
  useDeleteTemplate: () => ({ mutate: remove, isPending: false }),
  openTemplatePreview: vi.fn(),
}));

describe("RenderingSettingsPage", () => {
  beforeEach(() => {
    save.mockClear();
    upload.mockClear();
    remove.mockClear();
  });

  it("labels resets, saves template and fit choices, and manages custom templates", async () => {
    const user = userEvent.setup();
    render(<RenderingSettingsPage />, { wrapper: withQueryClient });
    expect(
      screen.getByRole("button", { name: /reset options/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reset custom templates/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^reset to defaults$/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/path|directory/i)).not.toBeInTheDocument();
    await user.click(screen.getByText("mine"));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(save).toHaveBeenLastCalledWith({ template: "custom:mine", fitOnePage: true });
    await user.click(screen.getByText("Classic"));
    await user.click(screen.getByRole("switch", { name: /fit resume to one page/i }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(save).toHaveBeenLastCalledWith({ template: "classic", fitOnePage: false });

    const file = new File(["hello"], "fresh.typ", { type: "text/plain" });
    await user.upload(screen.getByLabelText("Upload Typst template"), file);
    expect(upload).toHaveBeenCalledWith(file);
    await user.click(screen.getByRole("button", { name: "Delete mine template" }));
    expect(remove).toHaveBeenCalledWith("mine");
  });
});
