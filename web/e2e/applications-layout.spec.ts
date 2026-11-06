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
            cells: index === titles.length - 1 ? {
              application_submitted: {
                occurredAt: "2026-10-29T16:00:00Z",
                result: "advanced",
                interviewers: "Recruiting operations and platform infrastructure hiring panel",
              },
            } : {},
          })),
        } }));
        await page.goto("/applications");

        const table = page.getByRole("table");
        await expect(table).toBeVisible({ timeout: 15_000 });
        await expect(page.getByText(locale === "zh-CN" ? "符合条件的申请：4 条，共 4 条" : "Matching applications: 4 of 4")).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await expect(table.getByRole("columnheader", {
          name: locale === "zh-CN" ? "职位" : "Role", exact: true,
        })).toBeVisible();
        const controls = page.locator("section").filter({ has: page.locator("#application-company-search") });
        const fields = await controls.locator("input, select").evaluateAll((elements) =>
          elements.map((element) => ({ y: element.getBoundingClientRect().y, height: element.clientHeight })),
        );
        expect(fields).toHaveLength(3);
        expect(fields.every((field) => field.height === fields[0].height)).toBe(true);
        if (width >= 1440) expect(fields.every((field) => Math.abs(field.y - fields[0].y) <= 1)).toBe(true);

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
        if (width === 375 && locale === "en" && colorScheme === "light") {
          const date = table.getByRole("button", { name: "Application submitted details" });
          await date.click();
          const detail = page.getByText(/Recruiting operations and platform infrastructure hiring panel/);
          await expect(detail).toBeInViewport({ ratio: 1 });
          expect(await detail.evaluate((element) => {
            const { left, top, width, height } = element.getBoundingClientRect();
            return element.contains(document.elementFromPoint(left + width / 2, top + height / 2));
          })).toBe(true);
          await page.keyboard.press("Escape");
          await expect(detail).toHaveCount(0);
          await expect(date).toBeFocused();
        }
        await scroller.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
        await expect(table.getByRole("columnheader", {
          name: locale === "zh-CN" ? "其他" : "Other", exact: true,
        })).toBeInViewport();
        if (width === 1440 || (width === 2619 && locale === "zh-CN" && colorScheme === "dark")) {
          await scroller.evaluate((element) => { element.scrollLeft = 0; });
          await scroller.screenshot({ path: testInfo.outputPath(`applications-${locale}-${colorScheme}.png`) });
          await controls.screenshot({ path: testInfo.outputPath(`application-filters-${locale}-${colorScheme}.png`) });
        }
      });
    }
  });
}
