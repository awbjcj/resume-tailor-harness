import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { StyleGuideSettingsPage } from "./StyleGuideSettingsPage";

describe("StyleGuideSettingsPage", () => {
  it("saves markdown and replaces unsaved edits after a confirmed reset", async () => {
    let content = "Original";
    let lastPut: { content: string } | null = null;
    server.use(
      http.get("/api/config/style-guide", () => HttpResponse.json({ content })),
      http.put("/api/config/style-guide", async ({ request }) => {
        lastPut = (await request.json()) as { content: string };
        content = lastPut.content;
        return HttpResponse.json(lastPut);
      }),
      http.post("/api/settings/sections/style_guide/reset", () => {
        content = "Default style";
        return HttpResponse.json({ id: "style_guide", label: "Style guide", customized: false });
      }),
    );
    const user = userEvent.setup();
    render(<StyleGuideSettingsPage />, { wrapper: withQueryClient });
    const box = await screen.findByLabelText("Style guide");
    await user.type(box, "\nBe concrete.");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(lastPut?.content).toContain("Be concrete."));
    await waitFor(() => expect(screen.queryByText("You have unsaved changes")).not.toBeInTheDocument());
    await user.type(box, " unsaved");
    await user.click(screen.getByRole("button", { name: "Reset to defaults" }));
    await user.click(screen.getByRole("button", { name: "Reset" }));
    await waitFor(() => expect(screen.getByLabelText("Style guide")).toHaveValue("Default style"));
    expect(screen.queryByText("You have unsaved changes")).not.toBeInTheDocument();
  });
});
