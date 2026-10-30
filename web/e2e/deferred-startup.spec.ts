import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";

test.beforeEach(async ({ page }) => {
  await mockEmptyRuns(page);
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/board-views*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/triage*", (route) => route.fulfill({ json: {
    data: [], total: 0, facets: {}, pagination: { page: 1, pageSize: 50, totalItems: 0, totalPages: 1 },
  } }));
});

for (const language of ["en", "zh-CN"] as const) {
  test(`failed form download offers localized reload recovery: ${language}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("resume-tailor-harness-language", value), language);
    let attempts = 0;
    await page.route("**/assets/ManualJobForm-*.js", (route) => ++attempts === 1 ? route.abort("failed") : route.continue());
    await page.goto("/triage");
    const trigger = page.locator("header.app-chrome").getByRole("button", { name: language === "en" ? "Add job manually" : "手动添加职位", exact: true });
    await trigger.click();
    await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
    await page.getByRole("button", { name: language === "en" ? "Reload page" : "重新加载页面", exact: true }).click();
    await trigger.click();
    await expect(page.getByRole("dialog").locator('[name="title"]')).toBeVisible();
    expect(attempts).toBe(2);
  });
  for (const width of [320, 1440]) {
    test(`delayed forms retain focus and drafts: ${language}, ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem("resume-tailor-harness-language", value), language);
      const requested: string[] = [];
      const errors: string[] = [];
      page.on("request", (request) => requested.push(request.url()));
      page.on("pageerror", (error) => errors.push(error.message));
      let release!: () => void;
      const wait = new Promise<void>((resolve) => { release = resolve; });
      await page.route("**/assets/ManualJobForm-*.js", async (route) => { await wait; await route.continue(); });
      await page.goto("/triage");
      const trigger = page.locator("header.app-chrome").getByRole("button", { name: language === "en" ? "Add job manually" : "手动添加职位", exact: true });
      await expect(trigger).toBeVisible();
      expect(requested.some((url) => /(?:ManualJobForm|AddUrlForm|ImportJobsForm|EmailDraftForm)-/.test(url))).toBe(false);
      await trigger.click();
      await expect(page.getByRole("dialog").getByRole("status")).toHaveText(language === "en" ? "Loading…" : "正在加载…");
      release();
      const title = page.getByRole("dialog").locator('[name="title"]');
      await expect(title).toBeVisible();
      await expect.poll(() => page.getByRole("dialog").evaluate((element) => element.contains(document.activeElement))).toBe(true);
      await title.fill("Preserved draft");
      await page.keyboard.press("Escape");
      await expect(trigger).toBeFocused();
      await trigger.click();
      await expect(title).toHaveValue("Preserved draft");
      await page.setViewportSize({ width: width === 320 ? 1440 : 320, height: 900 });
      await expect(title).toHaveValue("Preserved draft");
      await expect.poll(() => page.getByRole("dialog").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      expect(errors).toEqual([]);
    });
  }
}

test("public login avoids the authenticated workspace and optional forms", async ({ page }) => {
  const requested: string[] = [];
  page.on("request", (request) => requested.push(request.url()));
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /sign in/i, exact: true })).toBeVisible();
  expect(requested.some((url) => /(?:AppLayout|ManualJobForm|AddUrlForm|ImportJobsForm|EmailDraftForm)-/.test(url))).toBe(false);
});

test("workspace offers an explicit reload for a cached module fetch failure", async ({ page }) => {
  let attempts = 0;
  await page.route("**/assets/AppLayout-*.js", (route) => ++attempts === 1 ? route.abort("failed") : route.continue());
  await page.goto("/triage");
  await expect(page.getByRole("alert")).toHaveText("The workspace could not load. Try again.");
  await page.getByRole("button", { name: "Reload page", exact: true }).click();
  await expect(page.locator("header.app-chrome").getByRole("button", { name: "Add job manually", exact: true })).toBeVisible();
  expect(attempts).toBe(2);
});
