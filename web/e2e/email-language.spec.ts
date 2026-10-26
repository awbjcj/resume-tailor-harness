import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";
import { emailNotificationsZh } from "../src/i18n/email-notifications";

for (const { width, theme } of [{ width: 1280, theme: "light" }, { width: 390, theme: "dark" }]) {
  test(`dashboard language changes are saved for outgoing emails at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.addInitScript((preferredTheme) => {
      localStorage.setItem("resume-tailor-harness-language", "en");
      localStorage.setItem("theme", preferredTheme);
    }, theme);
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
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/email-notifications-zh-CN-${width}.png`, fullPage: true });
    await page.getByRole("switch", { name: emailNotificationsZh.statistics, exact: true }).click();
    await expect(page.getByRole("button", { name: "保存更改", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "放弃", exact: true }).click();
    await expect(page.getByRole("switch", { name: emailNotificationsZh.statistics, exact: true })).toBeChecked();
    await expect(page.getByRole("button", { name: "保存更改", exact: true })).toHaveCount(0);
    await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
    await expect(page.getByRole("heading", { name: "Email notifications", exact: true })).toBeVisible();
    await expect.poll(() => savedLanguage).toBe("en");
  });
}
