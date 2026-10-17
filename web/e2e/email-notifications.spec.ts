import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";

for (const width of [1280, 390]) {
  test(`notification preferences and verification at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "en"));
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await mockEmptyRuns(page);
    await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
    await page.route("**/api/notifications*", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
    let preference = {
      email: "", enabled: false, frequency: "weekly", pendingReviews: true,
      statistics: true, reminders: true, verifiedAt: null as string | null,
      verificationPending: false, nextSendAt: null as string | null, lastSentAt: null,
      deliveryAvailable: true, deliveryFailed: false,
    };
    await page.route("**/api/email-notifications", async (route) => {
      if (route.request().method() === "PUT") preference = { ...preference, ...route.request().postDataJSON() };
      await route.fulfill({ json: preference });
    });
    await page.route("**/api/email-notifications/verification", async (route) => {
      preference.verificationPending = true;
      await route.fulfill({ json: { status: "sent" } });
    });
    await page.route("**/api/email-notifications/verify", async (route) => {
      expect(route.request().postDataJSON()).toEqual({ email: "review@example.com", code: "123456" });
      preference = { ...preference, verifiedAt: "2026-10-16T12:00:00Z", nextSendAt: "2026-10-17T12:00:00Z", verificationPending: false };
      await route.fulfill({ json: preference });
    });
    await page.goto("/settings/notifications");
    await expect(page.getByRole("heading", { name: "Email notifications" })).toBeVisible();
    await page.getByLabel("Notification email address", { exact: true }).fill("review@example.com");
    await page.getByRole("switch", { name: "Send me email notifications" }).click();
    await page.getByRole("radio", { name: "Weekly", exact: true }).focus();
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByRole("radio", { name: "Daily", exact: true })).toBeChecked();
    await expect(page.getByRole("button", { name: "Discard", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/email-notifications-draft-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(page.getByRole("button", { name: "Discard", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Send verification code" }).click();
    await expect(page.getByText("Verification code sent. Check your inbox and spam folder.")).toBeVisible();
    await page.getByLabel("Six-digit verification code").fill("123456");
    await page.getByRole("button", { name: "Verify email" }).click();
    await expect(page.getByText("Email notifications are on.")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `test-results/email-notifications-${width}.png`, fullPage: true });
    const emailInput = page.getByLabel("Notification email address", { exact: true });
    await emailInput.fill("invalid");
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    expect(await emailInput.evaluate((input: HTMLInputElement) => input.validity.valid)).toBe(false);
    expect(preference.email).toBe("review@example.com");
    await page.getByRole("button", { name: "Turn off email notifications" }).click();
    await expect(page.getByText("Email notifications are off.")).toBeVisible();
    expect(errors).toEqual([]);
  });
}
