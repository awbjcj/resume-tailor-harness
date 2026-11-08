import { expect, test } from "@playwright/test";

import { mockEmptyRuns } from "./support";

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
