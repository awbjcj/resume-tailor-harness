import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { GmailCard } from "./GmailCard";

describe("GmailCard", () => {
  it("offers reconnect even when both scopes are present", async () => {
    server.use(http.get("*/api/gmail/status", () => HttpResponse.json({
      connected: true, scopes: [], draftCapable: true, clientSource: "platform",
    })));
    render(<GmailCard />, { wrapper: withQueryClient });
    expect(await screen.findByRole("button", { name: "Reconnect" })).toBeInTheDocument();
  });

  it("distinguishes a temporary status failure from a disconnected account", async () => {
    server.use(http.get("*/api/gmail/status", () => HttpResponse.json({
      error: { code: "GMAIL_API_ERROR", message: "Temporarily unavailable" },
    }, { status: 503 })));
    render(<GmailCard />, { wrapper: withQueryClient });
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByText(/your connection may still be active/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Gmail" })).not.toBeInTheDocument();
  });

  it("offers connect when disconnected", async () => {
    server.use(
      http.get("*/api/gmail/status", () =>
        HttpResponse.json({
          connected: false,
          scopes: [],
          draftCapable: false,
          clientSource: "platform",
        }),
      ),
    );
    render(<GmailCard />, { wrapper: withQueryClient });
    expect(
      await screen.findByRole("button", { name: /connect gmail/i }),
    ).toBeInTheDocument();
  });

  it("offers reconnect when compose scope is missing", async () => {
    server.use(
      http.get("*/api/gmail/status", () =>
        HttpResponse.json({
          connected: true,
          scopes: ["readonly"],
          draftCapable: false,
          clientSource: "own",
        }),
      ),
    );
    render(<GmailCard />, { wrapper: withQueryClient });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /reconnect/i }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /disconnect/i }),
    ).toBeInTheDocument();
  });
});
