import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";
import { changeLanguage } from "@/i18n";
import { server } from "@/test/server";
import { AdminDecisionsCard } from "./AdminDecisionsCard";

function setup({ enabled = false, keyConfigured = false, fail = false } = {}) {
  const writes: Record<string, unknown>[] = [];
  let saved = { enabled, keyConfigured, endpoint: "https://api.openai.com/v1/decisions", model: "gpt-6-luna" };
  server.use(
    http.get("/api/admin/routing/decisions", () => HttpResponse.json(saved)),
    http.put("/api/admin/routing/decisions", async ({ request }) => {
      const body = await request.json() as Record<string, unknown>;
      writes.push(body);
      if (fail) return HttpResponse.json({ error: { code: "INVALID_DECISIONS_CONFIG", message: "Invalid key" } }, { status: 422 });
      saved = { ...saved, enabled: Boolean(body.enabled), keyConfigured: body.apiKey === undefined ? saved.keyConfigured : Boolean(body.apiKey) };
      return HttpResponse.json(saved);
    }),
  );
  const rendered = render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><AdminDecisionsCard /></QueryClientProvider>);
  return { ...rendered, writes, user: userEvent.setup() };
}

describe("AdminDecisionsCard", () => {
  it("requires a direct key and an explicit save to enroll", async () => {
    const { user, writes } = setup();
    const toggle = await screen.findByRole("switch", { name: "Enable direct OpenAI Decisions" });
    expect(toggle).not.toBeChecked();
    expect(screen.getByText(/charges the API balance/)).toBeInTheDocument();
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Save classification settings" })).toBeDisabled();
    expect(writes).toHaveLength(0);
    await user.type(screen.getByLabelText("Direct OpenAI API key"), "sk-direct-test");
    await user.click(screen.getByRole("button", { name: "Save classification settings" }));
    await screen.findByText("Classification settings saved. Changes apply to new operations.");
    expect(writes).toEqual([{ enabled: true, apiKey: "sk-direct-test" }]);
    expect(screen.getByLabelText("Direct OpenAI API key")).toHaveValue("");
  });

  it("can disable without removing the saved key, or remove it explicitly", async () => {
    const { user, writes } = setup({ enabled: true, keyConfigured: true });
    await user.click(await screen.findByRole("switch"));
    await user.click(screen.getByRole("button", { name: "Save classification settings" }));
    await screen.findByText("Classification settings saved. Changes apply to new operations.");
    expect(writes[0]).toEqual({ enabled: false });
    await user.click(screen.getByRole("button", { name: "Remove Decisions key" }));
    await user.click(screen.getByRole("button", { name: "Save classification settings" }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]).toEqual({ enabled: false, apiKey: null });
  });

  it("retains the draft and displays save failures", async () => {
    const { user } = setup({ fail: true });
    await user.type(await screen.findByLabelText("Direct OpenAI API key"), "invalid-test");
    await user.click(screen.getByRole("switch"));
    await user.click(screen.getByRole("button", { name: "Save classification settings" }));
    expect(await screen.findByText("Could not save. Check the direct API key and try again.")).toBeInTheDocument();
    expect(screen.getByLabelText("Direct OpenAI API key")).toHaveValue("invalid-test");
    await user.click(screen.getByRole("button", { name: "Discard edits" }));
    expect(screen.getByRole("switch")).not.toBeChecked();
    expect(screen.getByLabelText("Direct OpenAI API key")).toHaveValue("");
  });

  it("localizes enrollment and billing in Chinese", async () => {
    await changeLanguage("zh-CN");
    setup();
    expect(await screen.findByRole("switch", { name: "启用 OpenAI Decisions 直连" })).toBeInTheDocument();
    expect(screen.getByText(/API 余额计费/)).toBeInTheDocument();
    expect(screen.getByLabelText("OpenAI 直连 API 密钥")).toHaveAttribute("type", "password");
  });

  it("has no automated accessibility violations", async () => {
    const { container } = setup();
    await screen.findByRole("switch");
    expect((await axe(container)).violations).toEqual([]);
  });
});
