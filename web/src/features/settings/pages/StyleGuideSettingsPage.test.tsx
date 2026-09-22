import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { StyleGuideSettingsPage } from "./StyleGuideSettingsPage";

describe("StyleGuideSettingsPage", () => {
  it("replaces unsaved edits after an explicitly confirmed reset", async () => {
    let content = "Original";
    server.use(
      http.get("/api/config/style-guide", () => HttpResponse.json({ content })),
      http.post("/api/settings/sections/style_guide/reset", () => {
        content = "Default style";
        return HttpResponse.json({ id: "style_guide", label: "Style guide", customized: false });
      }),
    );
    const user = userEvent.setup();
    render(<StyleGuideSettingsPage />, { wrapper: withQueryClient });
    await user.type(await screen.findByLabelText("Style guide"), " unsaved");
    await user.click(screen.getByRole("button", { name: "Reset to defaults" }));
    await user.click(screen.getByRole("button", { name: "Reset" }));
    await waitFor(() => expect(screen.getByLabelText("Style guide")).toHaveValue("Default style"));
    expect(screen.queryByText("You have unsaved changes")).not.toBeInTheDocument();
  });

  it("edits and saves the markdown content", async () => {
    let lastPut: { content: string } | null = null;
    server.use(
      http.get("/api/config/style-guide", () => HttpResponse.json({ content: "# Voice" })),
      http.put("/api/config/style-guide", async ({ request }) => {
        lastPut = (await request.json()) as { content: string };
        return HttpResponse.json(lastPut);
      }),
    );

    const user = userEvent.setup();
    render(<StyleGuideSettingsPage />, { wrapper: withQueryClient });
    const box = await waitFor(() => screen.getByLabelText("Style guide"));
    await user.type(box, "\nBe concrete.");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(lastPut?.content).toContain("Be concrete."));
  });
});
