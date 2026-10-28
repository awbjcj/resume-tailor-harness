import { expect, test } from "@playwright/test";

import { mockEmptyRuns } from "./support";

const titles = [
  "Software Engineer, Cooperative Multi-Agent Systems",
  "Senior Applied AI Engineer",
  "资深人工智能工程师（多智能体协作与平台基础设施）",
  "PlatformEngineering".repeat(6),
];

const appearances = [
  { locale: "zh-CN", colorScheme: "light" },
  { locale: "zh-CN", colorScheme: "dark" },
  { locale: "en", colorScheme: "light" },
  { locale: "en", colorScheme: "dark" },
] as const;

for (const { locale, colorScheme } of appearances) {
  test.describe(`${locale} / ${colorScheme}`, () => {
    test.use({ locale, colorScheme });

    for (const width of [2619, 1440, 1024, 768, 375]) {
      test(`shows complete application titles at ${width}px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 1000 });
        await mockEmptyRuns(page);
        await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
        await page.route(/\/api\/run-completions(?:\?.*)?$/, (route) => route.fulfill({ json: [] }));
        await page.route("**/api/setup/status", (route) => route.fulfill({ json: {
          secrets: { anyLlmKey: true },
          profile: { documentCount: 1, hasResume: true },
          search: { configured: true },
          sources: { enabledCount: 1 },
          complete: true,
        } }));
        await page.route("**/api/applications", (route) => route.fulfill({ json: {
          technicalRoundColumns: width === 1024 ? 3 : 0,
          rows: titles.map((title, index) => ({
            jobId: index + 1,
            company: ["OpenAI", "NVIDIA", "示例公司", "Platform Engineering Company"][index],
            title,
            status: "submitted",
            source: "manual",
            fitScore: null,
            overflowRounds: 0,
            customCount: 0,
            totalComp: null,
            compCurrency: null,
            offerDeadline: null,
            cells: {},
          })),
        } }));
        await page.goto("/applications");

        const table = page.getByRole("table");
        await expect(table).toBeVisible({ timeout: 15_000 });
        await page.evaluate(() => document.fonts.ready);
        await expect(table.getByRole("columnheader", {
          name: locale === "zh-CN" ? "职位" : "Role", exact: true,
        })).toBeVisible();

        // Layout geometry catches truncation and sticky-column overlap that
        // DOM-only component tests cannot detect.
        for (const title of titles) {
          const cell = table.getByRole("cell", { name: title, exact: true });
          await expect(cell).toBeVisible();
          const layout = await cell.evaluate((element) => {
            const text = element.firstElementChild ?? element;
            const company = element.previousElementSibling!;
            return {
              clipped: text.scrollWidth > text.clientWidth + 1 || text.scrollHeight > text.clientHeight + 1,
              overlapped: company.getBoundingClientRect().right > element.getBoundingClientRect().left + 1,
            };
          });
          expect(layout).toEqual({ clipped: false, overlapped: false });
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);

        const scroller = table.locator("..");
        await scroller.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
        await expect(table.getByRole("columnheader", {
          name: locale === "zh-CN" ? "其他" : "Other", exact: true,
        })).toBeInViewport();
        if (width === 1440 || (width === 2619 && locale === "zh-CN" && colorScheme === "dark")) {
          await scroller.evaluate((element) => { element.scrollLeft = 0; });
          await scroller.screenshot({ path: testInfo.outputPath(`applications-${locale}-${colorScheme}.png`) });
        }
      });
    }
  });
}
