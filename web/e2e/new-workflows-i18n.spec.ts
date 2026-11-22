import { expect, test } from "@playwright/test";

import { mockEmptyRuns, mockGmailSettings } from "./support";

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "zh-CN"));
  await mockEmptyRuns(page);
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
});

test("localizes the settings navigation guard when switching languages", async ({ page }) => {
  await page.route("**/api/config/search", (route) => route.fulfill({ json: {
    keywords: ["platform"], titles: ["Software Engineer"], locations: ["Remote"],
    remotePolicy: ["remote"], minSalary: null,
  } }));
  await page.goto("/settings/search");
  const salary = page.getByLabel("最低薪资", { exact: true });
  await salary.fill("120000");
  await page.getByRole("navigation", { name: "设置", exact: true }).getByRole("link", { name: "评审配置", exact: true }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByText("放弃未保存的更改并离开？")).toBeVisible();
  await expect(dialog.getByText("你的修改尚未保存。你可以继续编辑并保存，或放弃更改后离开此页面。")).toBeVisible();
  await dialog.getByRole("button", { name: "继续编辑" }).click();
  await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
  await expect(page.getByLabel("Minimum salary", { exact: true })).toHaveValue("120000");
  await page.getByRole("navigation", { name: "Settings", exact: true }).getByRole("link", { name: "Review panel", exact: true }).click();
  await expect(dialog.getByText("Leave with unsaved changes?")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Discard and leave" })).toBeVisible();
  await dialog.getByRole("button", { name: "Keep editing" }).click();
});

test("explains job fetching and reprocessing in Chinese", async ({ page }) => {
  await page.route("**/api/triage?*", (route) => route.fulfill({ json: {
    data: [], pagination: { page: 1, pageSize: 200, totalItems: 0, totalPages: 1 }, facets: {}, total: 0,
  } }));
  await page.goto("/triage");
  await page.getByRole("button", { name: "获取", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("从所有已启用的连接器获取并导入职位。")).toBeVisible();
  await expect(dialog.getByText("本次从每个连接器获取的职位数量上限。留空表示不限制。")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "重新处理", exact: true }).click();
  await expect(dialog.getByText("重新对选定范围内的职位执行完整筛选。匹配分数和状态可能发生变化，已有进度的职位不会更改。")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "开始重新处理" })).toBeVisible();
});

test("localizes Gmail connection details and mobile navigation while switching languages", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockGmailSettings(page);
  await page.route("**/api/gmail/status", (route) => route.fulfill({ json: {
    connected: true, scopes: [], draftCapable: false, clientSource: "own",
  } }));
  await page.goto("/settings/notifications");

  await expect(page.getByText("已通过你自己的 OAuth 客户端连接。重新连接后即可创建草稿。")).toBeVisible();
  await page.getByRole("button", { name: "切换侧边栏" }).click();
  await expect(page.getByRole("dialog", { name: "侧边栏" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
  await expect(page.getByText("Connected using your own OAuth client. Reconnect to enable drafts.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Toggle Sidebar" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("formats quota dates in the selected language instead of the browser language", async ({ page }) => {
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: {
    username: "owner", role: "admin", authRequired: false,
  } }));
  await page.route("**/api/admin/quota-summary", (route) => route.fulfill({ json: {
    monthlySpendMicros: 0, monthlyCapMicros: 500000000, remainingMicros: 500000000,
    unpricedCallCount: 0, nextResetAt: "2026-12-01T00:00:00Z",
  } }));
  await page.route(/\/api\/admin\/(quota-tiers|quota-accounts|llm-rates|quota-operations)(?:\?.*)?$/, (route) => route.fulfill({ json: {
    data: [], pagination: { page: 1, pageSize: 100, totalItems: 0, totalPages: 1 },
  } }));
  const expected = await page.evaluate(() => {
    const instant = new Date("2026-12-01T00:00:00Z");
    const options: Intl.DateTimeFormatOptions = {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
    };
    return {
      chinese: instant.toLocaleString("zh-CN", options),
      english: instant.toLocaleString("en", options),
    };
  });

  await page.goto("/admin/quotas");
  await expect(page.getByText("下次重置", { exact: true })).toBeVisible();
  await expect(page.getByText(expected.chinese, { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
  await expect(page.getByText(expected.english, { exact: true })).toBeVisible();
});
