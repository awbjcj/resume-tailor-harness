import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { changeLanguage } from "@/i18n";
import { withQueryClient } from "@/test/utils";
import { EmailNotificationsPage } from "./EmailNotificationsPage";
import type { EmailPreferences } from "../use-email-notifications";

const DEFAULT: EmailPreferences = {
  email: "", enabled: false, frequency: "weekly", pendingReviews: true,
  statistics: true, reminders: true, verifiedAt: null, verificationPending: false,
  nextSendAt: null, lastSentAt: null, deliveryAvailable: true, deliveryFailed: false,
};

describe("EmailNotificationsPage", () => {
  it("saves opt-in preferences, verifies the address, and permits immediate opt-out", async () => {
    let state = { ...DEFAULT };
    let verification: unknown = null;
    let sends = 0;
    server.use(
      http.get("/api/email-notifications", () => HttpResponse.json(state)),
      http.put("/api/email-notifications", async ({ request }) => {
        state = { ...state, ...await request.json() as object };
        return HttpResponse.json(state);
      }),
      http.post("/api/email-notifications/verification", () => {
        sends++;
        state.verificationPending = true;
        return HttpResponse.json({ status: "sent" });
      }),
      http.post("/api/email-notifications/verify", async ({ request }) => {
        verification = await request.json();
        state = { ...state, verifiedAt: "2026-10-16T12:00:00Z", nextSendAt: "2026-10-17T12:00:00Z", verificationPending: false };
        return HttpResponse.json(state);
      }),
    );
    const user = userEvent.setup();
    render(<EmailNotificationsPage />, { wrapper: withQueryClient });
    await user.type(await screen.findByLabelText("Notification email address"), "me@example.com");
    await user.click(screen.getByRole("switch", { name: "Send me email notifications" }));
    await user.click(screen.getByRole("radio", { name: "Daily" }));
    await user.click(screen.getByRole("switch", { name: "Job-search statistics" }));
    await user.click(screen.getByRole("button", { name: "Save preferences" }));
    await screen.findByText("Verification required before delivery starts.");
    expect(state).toMatchObject({ email: "me@example.com", enabled: true, frequency: "daily", statistics: false });
    expect(sends).toBe(0);
    await user.click(screen.getByRole("button", { name: "Send verification code" }));
    await screen.findByText("Verification code sent. Check your inbox and spam folder.");
    await user.type(screen.getByLabelText("Six-digit verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify email" }));
    await screen.findByText("Email notifications are on.");
    expect(verification).toEqual({ email: "me@example.com", code: "123456" });
    // A partially edited invalid address cannot block opting out of saved consent.
    await user.clear(screen.getByLabelText("Notification email address"));
    await user.type(screen.getByLabelText("Notification email address"), "invalid");
    await user.click(screen.getByRole("button", { name: "Turn off email notifications" }));
    await screen.findByText("Email notifications are off.");
    expect(state).toMatchObject({ email: "me@example.com", enabled: false });
  });

  it("shows delivery configuration failures and permits opt-out", async () => {
    let saved: unknown = null;
    server.use(
      http.get("/api/email-notifications", () => HttpResponse.json({ ...DEFAULT, email: "me@example.com", enabled: true, deliveryAvailable: false })),
      http.put("/api/email-notifications", async ({ request }) => {
        saved = await request.json();
        return HttpResponse.json({ ...DEFAULT, ...saved as object });
      }),
    );
    render(<EmailNotificationsPage />, { wrapper: withQueryClient });
    expect(await screen.findByText(/Email delivery is not configured/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send verification code" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Turn off email notifications" }));
    await waitFor(() => expect(saved).toMatchObject({ enabled: false }));
  });

  it("keeps verification errors visible and blocks verification of unsaved addresses", async () => {
    server.use(
      http.get("/api/email-notifications", () => HttpResponse.json({ ...DEFAULT, email: "me@example.com", enabled: true, verificationPending: true })),
      http.post("/api/email-notifications/verify", () => HttpResponse.json({ error: { code: "INVALID_CODE", message: "The code is invalid or expired." } }, { status: 400 })),
    );
    const user = userEvent.setup();
    render(<EmailNotificationsPage />, { wrapper: withQueryClient });
    await user.type(await screen.findByLabelText("Six-digit verification code"), "111111");
    await user.click(screen.getByRole("button", { name: "Verify email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The code is invalid or expired.");
    await user.type(screen.getByLabelText("Notification email address"), "x");
    expect(screen.getByRole("button", { name: "Verify email" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Resend verification code" })).toBeDisabled();
  });

  it("explains digest and account notices in Chinese and localizes verification errors", async () => {
    await changeLanguage("zh-CN");
    server.use(
      http.get("/api/email-notifications", () => HttpResponse.json({ ...DEFAULT, email: "me@example.com", enabled: true, verificationPending: true })),
      http.post("/api/email-notifications/verify", () => HttpResponse.json({ error: { code: "INVALID_CODE", message: "The code is invalid or expired. Request a new code." } }, { status: 400 })),
    );
    const user = userEvent.setup();
    render(<EmailNotificationsPage />, { wrapper: withQueryClient });
    expect(await screen.findByText("邮件语言与界面语言设置一致。")).toBeInTheDocument();
    expect(screen.getByText("求职摘要邮件可随时关闭。账户和安全通知仍会发送至注册邮箱。")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "接收求职摘要邮件" })).toBeChecked();
    await user.type(screen.getByLabelText("6 位验证码"), "111111");
    await user.click(screen.getByRole("button", { name: /^验证邮箱$/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("验证码不正确或已过期，请重新获取。");
  });
});
