import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { GmailCard } from "./GmailCard";

describe("GmailCard", () => {
  it("saves the opt-in and allows it to be switched back off", async () => {
    const user = userEvent.setup();
    let enabled = false;
    server.use(
      http.get("*/api/gmail/status", () => HttpResponse.json({
        connected: true, scopes: [], draftCapable: true, clientSource: "platform",
        autoApplyRejections: enabled,
      })),
      http.put("*/api/gmail/automation", async ({ request }) => {
        const body = await request.json() as { autoApplyRejections: boolean };
        enabled = body.autoApplyRejections;
        return HttpResponse.json(body);
      }),
    );
    render(<GmailCard />, { wrapper: withQueryClient });
    const toggle = await screen.findByRole("switch", { name: "Auto-apply confirmed rejections" });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    await waitFor(() => expect(toggle).toBeChecked());
    await waitFor(() => expect(toggle).toBeEnabled());
    await user.click(toggle);
    await waitFor(() => expect(toggle).not.toBeChecked());
  });

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
    expect(screen.getByRole("button", { name: "Sync Gmail" })).toBeDisabled();
  });

  it("starts a manual sync from email settings and shows a failed launch inline", async () => {
    const user = userEvent.setup();
    let launches = 0;
    server.use(
      http.get("*/api/gmail/status", () => HttpResponse.json({
        connected: true, scopes: [], draftCapable: true, clientSource: "platform",
      })),
      http.post("*/api/gmail/sync", () => {
        launches += 1;
        return HttpResponse.json({ error: { code: "GMAIL_API_ERROR", message: "Please reconnect Gmail." } }, { status: 503 });
      }),
    );
    render(<GmailCard />, { wrapper: withQueryClient });
    await waitFor(() => expect(screen.getByRole("button", { name: "Sync Gmail" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Sync Gmail" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please reconnect Gmail.");
    expect(launches).toBe(1);
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
