import { expect, test } from "@playwright/test";
import { mockEmptyRuns, mockGmailSettings } from "./support";

for (const language of ["en", "zh-CN"]) {
  for (const { width, height, theme } of [
    { width: 375, height: 900, theme: "light" },
    { width: 1280, height: 900, theme: "dark" },
    { width: 844, height: 390, theme: "dark" },
  ]) {
    test(`mailbox setup in ${language} at ${width}px (${theme})`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.addInitScript(({ language, theme }) => {
        localStorage.setItem("resume-tailor-harness-language", language);
        localStorage.setItem("theme", theme);
      }, { language, theme });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await mockEmptyRuns(page);
      await mockGmailSettings(page);
      await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
      await page.route("**/api/notifications*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/email-notifications", (route) => route.fulfill({ json: {
        email: "", enabled: false, frequency: "weekly", pendingReviews: true, statistics: true, reminders: true,
        verifiedAt: null, verificationPending: false, nextSendAt: null, lastSentAt: null, deliveryAvailable: true,
      } }));
      let connected = false;
      let attempts = 0;
      await page.route("**/api/mailboxes", async (route) => {
        if (route.request().method() === "POST") {
          const body = route.request().postDataJSON();
          expect(body.imap.host).toBe("imap.mail.yahoo.com");
          expect(body.imap.password).toBe("test-app-password");
          expect(body.smtp).toBeNull();
          if (++attempts === 1) return route.fulfill({ status: 422, json: { error: {
            code: "MAILBOX_CREDENTIALS", message: "IMAP sign-in failed.",
            details: [{ loc: ["body", "imap", "password"], type: "MAILBOX_CREDENTIALS" }],
          } } });
          connected = true;
          return route.fulfill({ status: 201, json: { id: "test", provider: "yahoo", email: "test@yahoo.com" } });
        }
        return route.fulfill({ json: {
          providers: [
            { id: "microsoft", name: "Outlook / Microsoft 365", auth: "oauth", available: false },
            { id: "yahoo", name: "Yahoo Mail", auth: "password", available: true, imapHost: "imap.mail.yahoo.com", smtpHost: "smtp.mail.yahoo.com", smtpPort: 465, smtpSecurity: "tls" },
            { id: "custom", name: "Custom IMAP / SMTP", auth: "password", available: true },
          ],
          accounts: connected ? [{ id: "test", provider: "yahoo", email: "test@yahoo.com", folder: "INBOX" }] : [],
        } });
      });
      await page.goto("/settings/notifications");
      const zh = language === "zh-CN";
      await page.getByRole("button", { name: zh ? "添加邮箱账户" : "Add email account" }).click();
      await expect(page.getByLabel(zh ? "邮箱服务商" : "Email provider", { exact: true })).toBeFocused();
      await page.getByLabel(zh ? "邮箱服务商" : "Email provider", { exact: true }).selectOption("yahoo");
      await page.getByLabel(zh ? "邮箱地址" : "Mailbox email address", { exact: true }).fill("test@yahoo.com");
      await page.getByLabel(zh ? "应用专用密码" : "App password", { exact: true }).fill("test-app-password");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: `test-results/mailboxes-${language}-${width}.png`, fullPage: true });
      await page.getByRole("button", { name: zh ? "测试并连接" : "Test & connect" }).click();
      const summary = page.getByRole("alert").filter({ hasText: zh ? "登录失败" : "Sign-in failed" });
      await expect(summary).toBeFocused();
      const box = await summary.boundingBox();
      expect(box?.y).toBeGreaterThanOrEqual(0);
      expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(height);
      await page.screenshot({ path: `test-results/mailboxes-error-${language}-${width}.png` });
      await summary.getByRole("link").click();
      await expect(page.getByLabel(zh ? "应用专用密码" : "App password", { exact: true })).toBeFocused();
      await expect(page.getByLabel(zh ? "应用专用密码" : "App password", { exact: true })).toHaveValue("test-app-password");
      await page.getByRole("button", { name: zh ? "测试并连接" : "Test & connect" }).click();
      await expect(page.getByText("test@yahoo.com", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: zh ? "同步并分析" : "Sync & analyze" })).toBeVisible();
      await expect(page.getByLabel(zh ? "应用专用密码" : "App password", { exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: zh ? "添加邮箱账户" : "Add email account" })).toBeFocused();
      expect(errors).toEqual([]);
    });
  }
}
