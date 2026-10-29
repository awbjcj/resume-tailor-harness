import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { KeysSettingsPage } from "./KeysSettingsPage";

beforeEach(() => {
  server.use(
    http.get("/api/secrets", () => HttpResponse.json([
      { key: "openaiApiKey", isSet: false, hint: null },
      { key: "googleOauthClientId", isSet: false, hint: null },
      { key: "googleOauthClientSecret", isSet: false, hint: null },
    ])),
    http.get("/api/config/models", () => HttpResponse.json({
      cheapModel: "openai:test", midModel: "openai:test", premiumModel: "openai:test",
      cheapReasoningEffort: null, midReasoningEffort: null, premiumReasoningEffort: null,
    })),
    http.get("/api/config/models/catalog", () => HttpResponse.json([])),
  );
});

describe("KeysSettingsPage", () => {
  it("shows provider keys and models while keeping Gmail credentials on the email page", async () => {
    render(<MemoryRouter><KeysSettingsPage /></MemoryRouter>, { wrapper: withQueryClient });
    expect(await screen.findByRole("heading", { name: "API keys & models" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add OpenAI API key" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Model tiers" })).toBeInTheDocument();
    expect(screen.queryByText("Google OAuth client ID")).not.toBeInTheDocument();
    expect(screen.queryByText("Google OAuth client secret")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Gmail" })).not.toBeInTheDocument();
  });

  it("forwards old Gmail callback links with their outcome and other URL state intact", async () => {
    function Destination() {
      const location = useLocation();
      return <p>{location.pathname}{location.search}{location.hash}</p>;
    }
    render(
      <MemoryRouter initialEntries={["/settings/keys?gmail=denied&keep=1#connection"]}>
        <Routes>
          <Route path="/settings/keys" element={<KeysSettingsPage />} />
          <Route path="/settings/notifications" element={<Destination />} />
        </Routes>
      </MemoryRouter>,
      { wrapper: withQueryClient },
    );
    expect(await screen.findByText("/settings/notifications?gmail=denied&keep=1#connection")).toBeInTheDocument();
  });
});
