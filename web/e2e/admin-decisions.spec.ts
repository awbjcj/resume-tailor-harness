import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";

for (const [width, language, theme] of [[1280, "en", "light"], [375, "zh-CN", "dark"]] as const) {
  test(`direct Decisions enrollment at ${width}px in ${language} ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.addInitScript((locale) => localStorage.setItem("resume-tailor-harness-language", locale), language);
    await mockEmptyRuns(page);
    await page.route("**/api/auth/me", (route) => route.fulfill({ json: { username: "owner", role: "admin", authRequired: true, emailVerified: true, needsEmail: false } }));
    await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
    for (const path of ["notifications", "run-completions", "board-views"]) {
      await page.route(`**/api/${path}*`, (route) => route.fulfill({ json: [] }));
    }
    await page.route("**/api/admin/routing", (route) => {
      expect(route.request().method()).toBe("GET");
      return route.fulfill({ json: { baseUrl: "https://gateway.example.com", providers: [{ provider: "openai", label: "OpenAI", routeMode: "subscription", effectiveMode: "subscription", configurationError: null, key: { isSet: true, hint: "1234" } }] } });
    });
    let state = { enabled: false, keyConfigured: false, endpoint: "https://api.openai.com/v1/decisions", model: "gpt-6-luna" };
    const writes: Record<string, unknown>[] = [];
    await page.route("**/api/admin/routing/decisions", (route) => {
      if (route.request().method() === "PUT") {
        const body = route.request().postDataJSON();
        writes.push(body);
        state = { ...state, enabled: body.enabled, keyConfigured: body.apiKey === undefined ? state.keyConfigured : Boolean(body.apiKey) };
      }
      return route.fulfill({ json: state });
    });
    await page.goto("/admin/routing");
    const zh = language === "zh-CN";
    const toggle = page.getByRole("switch", { name: zh ? "启用 OpenAI Decisions 直连" : "Enable direct OpenAI Decisions" });
    const key = page.getByLabel(zh ? "OpenAI 直连 API 密钥" : "Direct OpenAI API key");
    const save = page.getByRole("button", { name: zh ? "保存分类设置" : "Save classification settings" });
    await expect(toggle).not.toBeChecked();
    await toggle.click();
    await expect(save).toBeDisabled();
    await key.fill("test-only-direct-key");
    await save.click();
    await expect(key).toHaveValue("");
    await expect(toggle).toBeChecked();
    expect(writes).toEqual([{ enabled: true, apiKey: "test-only-direct-key" }]);
    expect(await page.locator("body").innerText()).not.toContain("test-only-direct-key");
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("test-only-direct-key");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/decisions-${language}-${width}.png`, fullPage: true });
    await toggle.click();
    await save.click();
    await expect(save).toBeDisabled();
    expect(writes[1]).toEqual({ enabled: false });
  });
}
