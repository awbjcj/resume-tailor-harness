import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";

for (const [width, language, theme] of [[1280, "en", "light"], [375, "zh-CN", "light"], [768, "en", "dark"], [375, "zh-CN", "dark"]] as const) {
  test(`password manager at ${width}px in ${language} ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.addInitScript((locale) => localStorage.setItem("resume-tailor-harness-language", locale), language);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await mockEmptyRuns(page);
    await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
    for (const path of ["notifications", "run-completions", "board-views"]) {
      await page.route(`**/api/${path}*`, (route) => route.fulfill({ json: [] }));
    }
    let saved = false;
    let enabled = false;
    const account = { id: "one", company: "Example Company", origin: "https://careers.example.com", username: "applicant@example.com", status: "active", revision: 1, createdAt: "2026-10-29", updatedAt: "2026-10-29", lastUsedAt: null };
    await page.route("**/api/application-accounts", async (route) => {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        expect(body.password).toBe("test-only-secret!");
        saved = true;
        return route.fulfill({ json: account });
      }
      return route.fulfill({ json: { configured: true, autoRegister: enabled, revision: saved ? 2 : 1, accounts: saved ? [account] : [] } });
    });
    await page.route("**/api/application-accounts/policy", async (route) => {
      enabled = route.request().postDataJSON().autoRegister;
      return route.fulfill({ json: { configured: true, autoRegister: enabled, revision: 1, accounts: [] } });
    });
    await page.route("**/api/application-accounts/one*", async (route) => {
      if (route.request().method() === "DELETE") {
        saved = false;
        return route.fulfill({ status: 204 });
      }
      return route.fulfill({ json: { ...account, revision: 2 } });
    });
    await page.goto("/settings/password-manager");
    const zh = language === "zh-CN";
    await expect(page.getByRole("heading", { name: zh ? "密码管理器" : "Password manager", exact: true })).toBeVisible();
    await page.getByRole("switch").click();
    await expect(page.getByRole("switch")).toBeChecked();
    await page.getByLabel(zh ? "雇主" : "Employer", { exact: true }).fill("Example Company");
    await page.getByLabel(zh ? "HTTPS 登录网址" : "HTTPS login URL").fill(account.origin + "/login");
    await page.getByLabel(zh ? "邮箱或用户名" : "Email or username").fill(account.username);
    const password = page.getByLabel(zh ? "密码" : "Password", { exact: true });
    await password.fill("test-only-secret!");
    await expect(password).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: zh ? "保存账号" : "Save account", exact: true }).click();
    await expect(page.getByText(account.username, { exact: true })).toBeVisible();
    await expect(password).toHaveValue("");
    expect(await page.locator("body").innerText()).not.toContain("test-only-secret!");
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("test-only-secret!");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole("heading", { name: zh ? "密码管理器" : "Password manager", exact: true }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(page.getByText(zh ? "账号已保存。" : "Account saved.", { exact: true })).not.toBeVisible();
    await page.screenshot({ path: `test-results/password-manager-${language}-${width}-${theme}.png`, fullPage: true });
    await page.getByRole("button", { name: zh ? "更新密码" : "Update password", exact: true }).click();
    const updatedPassword = page.getByLabel(zh ? "雇主网站的当前密码" : "Current password on the employer site");
    await expect(updatedPassword).toBeFocused();
    await updatedPassword.fill("replacement-test-only!");
    await page.getByRole("button", { name: zh ? "保存密码" : "Save password", exact: true }).click();
    await expect(page.getByRole("heading", { name: zh ? "已保存的账号" : "Saved accounts", exact: true })).toBeFocused();
    await page.getByRole("button", { name: zh ? "移除" : "Remove", exact: true }).click();
    await expect(page.getByRole("button", { name: zh ? "取消" : "Cancel", exact: true })).toBeFocused();
    await page.getByRole("button", { name: zh ? "移除登录信息" : "Remove saved login", exact: true }).click();
    await expect(page.getByText(account.username, { exact: true })).not.toBeVisible();
    expect(errors).toEqual([]);
  });
}
