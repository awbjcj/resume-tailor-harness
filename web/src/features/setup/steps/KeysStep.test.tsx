import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { server } from "@/test/server";
import type { SetupProvider } from "../use-setup-provider";
import { KeysStep } from "./KeysStep";

const config: SetupProvider = {
  providers: [
    { id: "openai", label: "OpenAI", available: true },
    { id: "gemini", label: "Gemini", available: true },
  ],
  selectedProvider: "openai",
  modelTiersReady: true,
  customEndpointAllowed: true,
  customEndpoint: null,
};

function renderKeys() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(["setup-provider"], config);
  render(<QueryClientProvider client={client}><MemoryRouter><KeysStep /></MemoryRouter></QueryClientProvider>);
  return (data: SetupProvider) => act(() => client.setQueryData(["setup-provider"], data));
}

beforeEach(() => server.use(http.get("/api/secrets", () => HttpResponse.json([]))));

describe("provider setup drafts", () => {
  it("follows a refreshed provider when the form has no edits", async () => {
    const refresh = renderKeys();
    expect(screen.getByLabelText("AI provider", { exact: true })).toHaveValue("openai");
    refresh({ ...config, selectedProvider: "gemini" });
    await waitFor(() => expect(screen.getByLabelText("AI provider", { exact: true })).toHaveValue("gemini"));
    expect(screen.getByRole("button", { name: /^Continue$/ })).toBeEnabled();
  });

  it("retains edited credentials when provider availability refreshes", async () => {
    const refresh = renderKeys();
    await userEvent.type(screen.getByLabelText("API key (optional)"), "draft-key");
    refresh({ ...config, selectedProvider: "gemini" });
    await waitFor(() => expect(screen.getByLabelText("API key (optional)")).toHaveValue("draft-key"));
    expect(screen.getByLabelText("AI provider", { exact: true })).toHaveValue("openai");
    expect(screen.getByRole("button", { name: "Save & continue" })).toBeEnabled();
  });
});
