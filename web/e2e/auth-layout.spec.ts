import { expect, test } from "@playwright/test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const routes = [
  "/login", "/register", "/forgot-password", "/complete-profile",
  "/verify-email?email=applicant@example.com", "/reset-password?email=applicant@example.com",
];

for (const { width, height, language, theme, enlarged } of [
  { width: 1440, height: 900, language: "en", theme: "light" },
  { width: 1920, height: 1080, language: "en", theme: "dark" },
  { width: 375, height: 812, language: "zh-CN", theme: "dark" },
  { width: 768, height: 1024, language: "en", theme: "light" },
  { width: 844, height: 390, language: "en", theme: "dark" },
  { width: 320, height: 900, language: "zh-CN", theme: "light", enlarged: true },
]) {
  test(`auth pages reflow at ${width}px in ${language}${enlarged ? " with enlarged text" : ""}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.addInitScript(({ language, theme }) => {
      localStorage.setItem("resume-tailor-harness-language", language);
      localStorage.setItem("theme", theme);
    }, { language, theme });
    await page.route("**/api/health", (route) => route.fulfill({ json: { googleOauthConfigured: true } }));
    await page.route("**/api/auth/me", (route) => route.fulfill({ json: { username: null, authRequired: true } }));
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (const route of routes) {
      await page.goto(route);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      if (enlarged) await page.addStyleTag({ content: "html { font-size: 200%; }" });
      await expect(page.getByRole("main")).toHaveCount(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const card = page.locator(".auth-card");
      const bounds = await card.boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
      expect(await card.evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
      const submit = page.locator('button[type="submit"]');
      if (route === "/login" && width >= 1440) await expect(submit).toBeInViewport();
      await submit.scrollIntoViewIfNeeded();
      await expect(submit).toBeInViewport();
      await page.evaluate(() => scrollTo(0, 0));
      if (route === "/login" || route === "/register") {
        await page.screenshot({ path: `test-results/auth-${route.slice(1)}-${language}-${width}.png`, fullPage: true });
      }
    }
    expect(errors).toEqual([]);
  });
}

test("login keeps keyboard access, localization, and error recovery above the canvas", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "en"));
  await page.route("**/api/health", (route) => route.fulfill({ json: { googleOauthConfigured: true } }));
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { username: null, authRequired: true } }));
  await page.route("**/api/auth/login", (route) => route.fulfill({ status: 401, json: {
    error: { code: "UNAUTHORIZED", message: "Invalid username or password" },
  } }));
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Continue with Google" })).toBeEnabled();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("combobox", { name: "Language", exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Continue with Google" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Email", { exact: true })).toBeFocused();
  await page.getByLabel("Email", { exact: true }).fill("test@example.com");
  await page.getByLabel("Password", { exact: true }).fill("invalid-test-password");
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("autocomplete", "current-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Invalid username or password");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  const violations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: () => Promise<{ violations: { id: string; nodes: unknown[] }[] }> } }).axe;
    return (await axe.run()).violations.map(({ id, nodes }) => ({ id, count: nodes.length }));
  });
  expect(violations).toEqual([]);
  await page.getByRole("combobox", { name: "Language", exact: true }).selectOption("zh-CN");
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  await page.getByRole("link", { name: "忘记密码？" }).click();
  await expect(page).toHaveURL(/\/forgot-password/);
});
