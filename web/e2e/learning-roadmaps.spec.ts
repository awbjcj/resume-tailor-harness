import { test, expect } from "@playwright/test";
import { mockEmptyRuns } from "./support";

for (const [width, language, theme] of [[375, "en", "light"], [768, "en", "light"], [844, "zh-CN", "dark"], [1440, "en", "dark"], [375, "zh-CN", "dark"], [1440, "zh-CN", "light"]] as const) {
  test(`learning roadmap management ${width} ${language} ${theme}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 844 ? 390 : 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.addInitScript(({ language, theme }) => {
      localStorage.setItem("resume-tailor-harness-language", language);
      localStorage.setItem("theme", theme);
    }, { language, theme });
    await mockEmptyRuns(page);
    await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
    await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
    let status = "planned";
    await page.route("**/api/learning-roadmaps", (route) => route.fulfill({ json: [{
      id: 7, label: "Platform engineering", status, available: true, envelope: { stale: false, suggestion: {
        kind: "domain", key: "platform", bridge: "Build on your existing infrastructure experience with a small deployment project.",
        repos: [{ name: "example/platform", url: "https://github.com/example/platform", why: "Study deployment patterns", stars: 1234 }],
        resources: [{ title: "Deployment documentation", url: "https://example.com/docs", kind: "doc" }],
        project: { title: "A reliable deployment pipeline", summary: "Build, deploy, monitor, and roll back a small service.", skillsDemonstrated: ["Containers", "Observability"] },
        citations: ["https://example.com/docs"], generatedAt: "2026-11-08T12:00:00Z",
      } },
    }] }));
    await page.route("**/api/learning-roadmaps/7", (route) => { status = route.request().postDataJSON().status; return route.fulfill({ status: 204 }); });
    await page.goto("/learning-roadmaps?plan=7");
    const detail = page.getByRole("region", { name: "Platform engineering", exact: true });
    await expect(detail.getByText("A reliable deployment pipeline")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(language === "en" ? "Learning roadmaps" : "学习路线");
    if (width < 1024) {
      await expect(detail.getByRole("heading", { name: "Platform engineering" })).toBeFocused();
      await detail.getByRole("button", { name: language === "en" ? "Back to roadmaps" : "返回学习路线列表" }).click();
      await expect(page.locator("#roadmap-list")).toBeFocused();
      await page.getByRole("link", { name: /Platform engineering/ }).click();
      await expect(detail.getByRole("heading", { name: "Platform engineering" })).toBeFocused();
    }
    await detail.getByRole("combobox").selectOption("in_progress");
    await expect(detail.getByRole("combobox")).toHaveValue("in_progress");
    await page.reload();
    await expect(detail.getByRole("combobox")).toHaveValue("in_progress");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("roadmaps.png"), fullPage: true });
    await detail.getByRole("combobox").selectOption("archived");
    await expect(page.getByText(language === "en" ? "No roadmaps match these filters." : "没有符合筛选条件的学习路线。")).toBeVisible();
    await detail.getByRole("combobox").selectOption("planned");
    await expect(page.getByRole("link", { name: /Platform engineering/ })).toBeVisible();
  });
}
