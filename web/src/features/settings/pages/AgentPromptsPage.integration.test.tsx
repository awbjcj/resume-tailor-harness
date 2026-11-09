import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { AgentPromptsPage } from "./AgentPromptsPage";

let guidance: string | null;
const item = () => ({
  key: "tailor-writer", title: "Resume writer", stage: "tailoring",
  description: "Writes a resume.", instructions: ["Use verified facts."],
  guidance, editable: true,
});

describe("AgentPromptsPage saved drafts", () => {
  beforeEach(() => {
    guidance = "Saved guidance";
    server.use(
      http.get("/api/agents/prompts", () => HttpResponse.json([item()])),
      http.put("/api/agents/prompts/:key", async ({ request }) => {
        const body = await request.json() as { guidance: string };
        guidance = body.guidance.trim() || null;
        return HttpResponse.json(item());
      }),
      http.post("/api/settings/sections/agent_guidance/reset", () => {
        guidance = null;
        return HttpResponse.json({ id: "agent_guidance", label: "Agent prompts", customized: false });
      }),
    );
  });

  it("uses the server-normalized guidance after saving", async () => {
    const user = userEvent.setup();
    render(<AgentPromptsPage />, { wrapper: withQueryClient });
    await user.click(await screen.findByText("Resume writer"));
    const editor = screen.getByLabelText("Your guidance for Resume writer");
    await user.clear(editor);
    await user.type(editor, "  New guidance  ");
    await user.click(screen.getByRole("button", { name: "Save guidance" }));
    await waitFor(() => expect(editor).toHaveValue("New guidance"));
    expect(screen.getByRole("button", { name: "Save guidance" })).toBeDisabled();
  });

  it("clears dirty editors after the whole section is reset", async () => {
    const user = userEvent.setup();
    render(<AgentPromptsPage />, { wrapper: withQueryClient });
    await user.click(await screen.findByText("Resume writer"));
    const editor = screen.getByLabelText("Your guidance for Resume writer");
    await user.type(editor, " with unsaved changes");
    await user.click(screen.getByRole("button", { name: "Reset to defaults" }));
    await user.click(screen.getByRole("button", { name: "Reset" }));
    await waitFor(() => expect(screen.getByLabelText("Your guidance for Resume writer")).toHaveValue(""));
    expect(screen.getByRole("button", { name: "Save guidance" })).toBeDisabled();
  });
});
