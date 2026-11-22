import { test, expect, type Page } from "@playwright/test";
import { mockEmptyRuns } from "./support";

async function prepareRoadmaps(page: Page, language: string, theme: string) {
  await page.addInitScript(({ language, theme }) => {
    localStorage.setItem("resume-tailor-harness-language", language);
    localStorage.setItem("theme", theme);
  }, { language, theme });
  await mockEmptyRuns(page);
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
}

for (const [width, language, theme] of [[375, "en", "light"], [768, "en", "light"], [844, "zh-CN", "dark"], [1440, "en", "dark"], [375, "zh-CN", "dark"], [1440, "zh-CN", "light"]] as const) {
  test(`learning roadmap management ${width} ${language} ${theme}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 844 ? 390 : 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await prepareRoadmaps(page, language, theme);
    let status = "planned";
    let allowSave!: () => void;
    const canSave = new Promise<void>((resolve) => { allowSave = resolve; });
    await page.route("**/api/learning-roadmaps", (route) => route.fulfill({ json: [{
      id: 7, label: "Platform engineering", status, available: true, envelope: { stale: false, suggestion: {
        kind: "domain", key: "platform", bridge: "Build on your existing infrastructure experience with a small deployment project.",
        repos: [{ name: "example/platform", url: "https://github.com/example/platform", why: "Study deployment patterns", stars: 1234 }],
        resources: [{ title: "Deployment documentation", url: "https://example.com/docs", kind: "doc" }],
        project: { title: "A reliable deployment pipeline", summary: "Build, deploy, monitor, and roll back a small service.", skillsDemonstrated: ["Containers", "Observability"] },
        citations: ["https://example.com/docs"], generatedAt: "2026-11-08T12:00:00Z",
      } },
    }] }));
    await page.route("**/api/learning-roadmaps/7", async (route) => {
      await canSave;
      status = route.request().postDataJSON().status;
      await route.fulfill({ status: 204 });
    });
    await page.goto("/learning-roadmaps?plan=7");
    const detail = page.getByRole("region", { name: "Platform engineering", exact: true });
    await expect(detail.getByText("A reliable deployment pipeline")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(language === "en" ? "Learning roadmaps" : "学习路线");
    await expect(detail.getByText(language === "en" ? "Build on what you know" : "从已有经验入手")).toBeVisible();
    await expect(detail.getByText(language === "en" ? "Project idea" : "项目构想")).toBeVisible();
    await expect(detail.getByText(language === "en" ? "Documentation" : "文档", { exact: true })).toBeVisible();
    const title = detail.getByRole("heading", { name: "Platform engineering" });
    const back = page.getByRole("link", { name: language === "en" ? "Back to roadmaps" : "返回学习路线列表" });
    const roadmap = page.getByRole("link", { name: "Platform engineering" });
    const progress = detail.getByRole("combobox");
    await expect(title).toBeFocused();
    await progress.focus();
    await progress.selectOption("in_progress");
    await expect(detail.getByRole("status")).toHaveText(language === "en" ? "Saving progress…" : "正在保存进度…");
    await expect(progress).toBeDisabled();
    allowSave();
    await expect(progress).toBeEnabled();
    await expect(progress).toBeFocused();
    await expect(progress).toHaveValue("in_progress");
    await page.reload();
    await expect(progress).toHaveValue("in_progress");
    await progress.selectOption("completed");
    await expect(progress).toBeEnabled();
    await detail.locator("summary").press("Enter");
    await expect(detail.getByRole("link", { name: "https://example.com/docs" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("roadmap-detail.png"), fullPage: true });
    await back.click();
    await expect(roadmap).toBeFocused();
    const filter = page.getByRole("combobox", { name: language === "en" ? "Filter by progress" : "按学习进度筛选" });
    await expect(filter.locator('option[value="active"]')).toHaveText(language === "en" ? "Not archived" : "未归档");
    await roadmap.press("Enter");
    await expect(title).toBeFocused();
    await progress.selectOption("archived");
    await expect(progress).toBeEnabled();
    await back.click();
    await page.getByRole("button", { name: language === "en" ? "View archived roadmaps" : "查看已归档的学习路线" }).click();
    await expect(filter).toHaveValue("archived");
    await roadmap.click();
    await progress.selectOption("planned");
    await expect(progress).toBeEnabled();
    await back.click();
    await expect(page.getByText(language === "en" ? "No roadmaps match these filters." : "没有符合筛选条件的学习路线。")).toBeVisible();
    await page.getByRole("button", { name: language === "en" ? "Reset filters" : "重置筛选" }).click();
    await expect(roadmap).toBeVisible();
  });
}

test("roadmap cards fill partial rows and large libraries retain their place", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await prepareRoadmaps(page, "en", "light");
  const plans = Array.from({ length: 61 }, (_, index) => ({
    id: index + 1, label: `Platform skill ${index + 1}`, status: "planned", available: true,
    envelope: { stale: false, suggestion: {
      kind: "skill", key: `skill-${index + 1}`, bridge: "Practice with a small project.",
      repos: [], citations: [], project: null, generatedAt: "2026-11-08T12:00:00Z",
      resources: index === 14 ? [{ title: "InfrastructureAutomation".repeat(7), kind: "doc", url: "https://example.com/docs" }] : [],
    } },
  }));
  let count = 0;
  await page.route("**/api/learning-roadmaps", (route) => route.fulfill({ json: plans.slice(0, count) }));
  await page.goto("/learning-roadmaps");
  await expect(page.getByRole("link", { name: "Explore skill gaps" })).toHaveAttribute("href", "/match-gap");
  await expect(page.getByRole("heading", { name: "No roadmaps yet" })).toBeVisible();

  const library = page.getByRole("region", { name: "Saved roadmaps" });
  const cards = library.getByRole("listitem");
  for (count of [1, 2, 5]) {
    await page.reload();
    await expect(cards).toHaveCount(count);
    const listRight = await library.getByRole("list").evaluate((list) => list.getBoundingClientRect().right);
    const rows = await cards.evaluateAll((items) => {
      const edges = new Map<number, number>();
      for (const item of items) {
        const { top, right } = item.getBoundingClientRect();
        edges.set(top, Math.max(right, edges.get(top) ?? 0));
      }
      return [...edges.values()];
    });
    expect(rows).toHaveLength(count === 5 ? 2 : 1);
    for (const right of rows) expect(Math.abs(right - listRight)).toBeLessThan(2);
  }

  count = 61;
  await page.goto("/learning-roadmaps?q=platform&status=planned&page=5");
  await expect(library.getByRole("status")).toHaveText("49–60 of 61 roadmaps");
  await expect(cards).toHaveCount(12);
  await library.getByRole("button", { name: "Next roadmap page" }).click();
  await expect(library.getByRole("status")).toHaveText("61 of 61 roadmaps");
  await expect(cards).toHaveCount(1);
  const finalPlan = library.getByRole("link", { name: "Platform skill 61" });
  await finalPlan.press("Enter");
  await expect(page.getByRole("heading", { name: "Platform skill 61" })).toBeFocused();
  await page.goBack();
  await expect(finalPlan).toBeFocused();
  await expect(library.getByRole("textbox", { name: "Search roadmaps" })).toHaveValue("platform");
  await expect(library.getByRole("combobox", { name: "Filter by progress" })).toHaveValue("planned");
  await finalPlan.click();
  await page.getByRole("link", { name: "Back to roadmaps" }).click();
  await expect(finalPlan).toBeFocused();
  await library.getByRole("textbox", { name: "Search roadmaps" }).fill("platform skill 15");
  const result = library.getByRole("link", { name: "Platform skill 15" });
  await expect(result).toBeVisible();
  await expect(cards).toHaveCount(1);
  await page.setViewportSize({ width: 320, height: 720 });
  await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
  await result.click();
  const resources = page.getByRole("region", { name: "Learning resources" });
  await expect(resources.getByRole("link")).toBeVisible();
  expect(await resources.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
