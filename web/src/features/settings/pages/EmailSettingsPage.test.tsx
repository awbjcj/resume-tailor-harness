import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { EmailSettingsPage } from "./EmailSettingsPage";

const SECRETS = [
  { key: "openaiApiKey", isSet: true, hint: "1234" },
  { key: "googleOauthClientId", isSet: false, hint: null },
  { key: "googleOauthClientSecret", isSet: false, hint: null },
];

beforeEach(() => {
  server.use(
    http.get("/api/mailboxes", () => HttpResponse.json({ providers: [], accounts: [] })),
    http.get("/api/secrets", () => HttpResponse.json(SECRETS)),
    http.get("/api/gmail/status", () => HttpResponse.json({
      connected: false, scopes: [], draftCapable: false, clientSource: "platform",
    })),
    http.get("/api/email-notifications", () => HttpResponse.json({
      email: "me@example.com", enabled: false, frequency: "weekly", pendingReviews: true,
      statistics: true, reminders: true, verifiedAt: null, verificationPending: false,
      nextSendAt: null, lastSentAt: null, deliveryAvailable: true, deliveryFailed: false,
    })),
  );
});

describe("EmailSettingsPage", () => {
  it("keeps Gmail, custom connection settings, and email preferences together with independent saves", async () => {
    const user = userEvent.setup();
    let patch: unknown;
    server.use(http.put("/api/secrets", async ({ request }) => {
      patch = await request.json();
      return HttpResponse.json(SECRETS);
    }));
    render(<MemoryRouter><EmailSettingsPage /></MemoryRouter>, { wrapper: withQueryClient });

    expect(screen.getByRole("heading", { level: 1, name: "Email & notifications" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Connect Gmail" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync Gmail" })).toBeDisabled();
    expect(await screen.findByRole("heading", { level: 2, name: "Email notifications" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Delivery status" })).toBeInTheDocument();
    expect(screen.getByText("Custom Gmail OAuth client (optional)").closest("details")).not.toHaveAttribute("open");

    await user.type(screen.getByLabelText("Notification email address", { exact: true }), ".draft");
    await user.click(screen.getByText("Custom Gmail OAuth client (optional)"));
    await user.click(await screen.findByRole("button", { name: "Add Google OAuth client ID" }));
    expect(screen.queryByText("OpenAI API key")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Google OAuth client ID new value"), "custom-client");
    await user.click(screen.getByRole("button", { name: "Save key" }));
    await waitFor(() => expect(patch).toEqual({ googleOauthClientId: "custom-client" }));
    expect(screen.getByLabelText("Notification email address", { exact: true })).toHaveValue("me@example.com.draft");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
  });

  it("keeps Gmail available if notification preferences cannot load", async () => {
    server.use(http.get("/api/email-notifications", () => HttpResponse.json({}, { status: 503 })));
    render(<MemoryRouter><EmailSettingsPage /></MemoryRouter>, { wrapper: withQueryClient });
    expect(await screen.findByText("Could not load email preferences.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Connect Gmail" })).toBeInTheDocument();
  });

  it("keeps notification preferences available if Gmail cannot load", async () => {
    server.use(http.get("/api/gmail/status", () => HttpResponse.json({}, { status: 503 })));
    render(<MemoryRouter><EmailSettingsPage /></MemoryRouter>, { wrapper: withQueryClient });
    expect(await screen.findByText(/your connection may still be active/)).toBeInTheDocument();
    expect(await screen.findByLabelText("Notification email address", { exact: true })).toHaveValue("me@example.com");
  });
});
