import { expect, test } from "@playwright/test";
import { mockEmptyRuns, mockGmailSettings } from "./support";

const COPY = {
  en: {
    nav: "Settings", picker: "Settings section", email: "Email & notifications",
    gmail: "Gmail connection & sync", preferences: "Email notifications",
    custom: "Custom Gmail OAuth client (optional)", clientId: "Add Google OAuth client ID",
    keys: "API keys & models", provider: "Add OpenAI API key",
    groups: ["Discovery", "Resumes", "Applications", "AI configuration", "Workspace"],
  },
  "zh-CN": {
    nav: "设置", picker: "设置分区", email: "邮件与通知",
    gmail: "Gmail 连接与同步", preferences: "邮件通知",
    custom: "自定义 Gmail OAuth 客户端（可选）", clientId: "添加 Google OAuth 客户端 ID",
    keys: "API 密钥与模型", provider: "添加 OpenAI API 密钥",
    groups: ["发现", "简历", "申请", "AI 配置", "工作区"],
  },
};

for (const language of ["en", "zh-CN"] as const) {
  for (const width of [375, 768, 1440]) {
    const theme = width === 1440 ? "light" : "dark";
    test(`related settings stay grouped in ${language} at ${width}px (${theme})`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.addInitScript(({ language, theme }) => {
        localStorage.setItem("resume-tailor-harness-language", language);
        localStorage.setItem("theme", theme);
      }, { language, theme });
      const copy = COPY[language];
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await mockEmptyRuns(page);
      await mockGmailSettings(page);
      await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
      await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/email-notifications", (route) => route.fulfill({ json: {
        email: "me@example.com", enabled: false, frequency: "weekly", pendingReviews: true,
        statistics: true, reminders: true, verifiedAt: null, verificationPending: false,
        nextSendAt: null, lastSentAt: null, deliveryAvailable: true, deliveryFailed: false,
      } }));
      await page.route("**/api/config/models", (route) => route.fulfill({ json: {
        cheapModel: "openai:test", midModel: "openai:test", premiumModel: "openai:test",
        cheapReasoningEffort: null, midReasoningEffort: null, premiumReasoningEffort: null,
      } }));
      await page.route("**/api/config/models/catalog", (route) => route.fulfill({ json: [] }));

      await page.goto("/settings/notifications");
      await expect(page.getByRole("heading", { level: 1, name: copy.email, exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { level: 2, name: copy.gmail })).toBeVisible();
      await expect(page.getByRole("heading", { level: 2, name: copy.preferences, exact: true })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      const nav = page.getByRole("navigation", { name: copy.nav, exact: true });
      if (width >= 1024) {
        for (const group of copy.groups) {
          await expect(nav.getByRole("list", { name: group, exact: true })).toBeVisible();
        }
        await expect(nav.getByRole("link", { name: copy.email, exact: true })).toHaveAttribute("aria-current", "page");
      } else {
        await expect(nav.getByRole("combobox", { name: copy.picker })).toHaveValue("/settings/notifications");
        await expect(nav.locator("optgroup")).toHaveCount(5);
      }
      await page.getByText(copy.custom, { exact: true }).click();
      await expect(page.getByRole("button", { name: copy.clientId, exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: copy.provider, exact: true })).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `test-results/settings-${language}-${width}.png`, fullPage: true });

      if (width >= 1024) {
        await nav.getByRole("link", { name: copy.keys, exact: true }).click();
      } else {
        await nav.getByRole("combobox", { name: copy.picker }).selectOption("/settings/keys");
      }
      await expect(page.getByRole("heading", { name: copy.keys, exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: copy.provider, exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: copy.clientId, exact: true })).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.goBack();
      await expect(page.getByRole("heading", { level: 1, name: copy.email, exact: true })).toBeVisible();
      if (width < 1024) {
        await expect(nav.getByRole("combobox", { name: copy.picker })).toHaveValue("/settings/notifications");
      } else {
        await page.setViewportSize({ width, height: 720 });
        const backup = nav.locator('a[href="/settings/backup"]');
        await backup.focus();
        await expect(backup).toBeFocused();
        await expect(backup).toBeInViewport({ ratio: 1 });
      }
      expect(errors).toEqual([]);
    });
  }
}
