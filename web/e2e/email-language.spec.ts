import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";
import { emailNotificationsZh } from "../src/i18n/email-notifications";

test("dashboard language changes are saved for outgoing emails", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "en"));
  await mockEmptyRuns(page);
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
  await page.route("**/api/notifications*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
  let savedLanguage = "";
  await page.route("**/api/config/language", async (route) => {
    savedLanguage = route.request().postDataJSON().language;
    await route.fulfill({ json: { language: savedLanguage } });
  });
  await page.route("**/api/email-notifications", (route) => route.fulfill({ json: {
    email: "me@example.com", enabled: true, frequency: "weekly", pendingReviews: true,
    statistics: true, reminders: true, verifiedAt: "2026-10-17T12:00:00Z",
    verificationPending: false, nextSendAt: "2026-10-24T12:00:00Z", lastSentAt: null,
    deliveryAvailable: true, deliveryFailed: false,
  } }));
  await page.goto("/settings/notifications");
  await expect.poll(() => savedLanguage).toBe("en");
  await page.getByRole("combobox", { name: "Language", exact: true }).selectOption("zh-CN");
  await expect(page.getByRole("heading", { name: "邮件通知", exact: true })).toBeVisible();
  await expect.poll(() => savedLanguage).toBe("zh-CN");
  await expect(page.getByLabel(emailNotificationsZh.email, { exact: true })).toHaveValue("me@example.com");
  await page.screenshot({ path: "test-results/email-notifications-zh-CN.png", fullPage: true });
  await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
  await expect(page.getByRole("heading", { name: "Email notifications", exact: true })).toBeVisible();
  await expect.poll(() => savedLanguage).toBe("en");
});
