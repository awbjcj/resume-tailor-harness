// Install all three engines before running: npx playwright install chromium firefox webkit
import { chromium, firefox, webkit, type Browser, expect, test } from "@playwright/test";
test.describe.configure({ mode: "parallel" });
for (const browserName of ["chromium", "firefox", "webkit"] as const) {
    test.describe(browserName, () => {
        let browser: Browser;
        test.beforeAll(async () => { browser = await ({ chromium, firefox, webkit })[browserName].launch(); });
        test.afterAll(async () => { await browser?.close(); });
        for (const language of ["en", "zh-CN"])
            for (const width of [320, 390, 768, 844, 1024, 1440, 1920]) {
                test(`${language} compact panels at ${width}px`, async ({ baseURL }, testInfo) => {
                    const page = await browser.newPage({ baseURL });
                    await page.setViewportSize({ width, height: width === 844 ? 390 : 900 });
                    await page.emulateMedia({ reducedMotion: "reduce" });
                    await page.addInitScript(({ language }) => {
                        localStorage.setItem("resume-tailor-harness-language", language);
                        localStorage.setItem("theme", language === "en" ? "light" : "dark");
                    }, { language });
                    const errors: string[] = [];
                    page.on("pageerror", error => errors.push(error.message));
                    await page.route("**/api/**", route => {
                        const path = new URL(route.request().url()).pathname;
                        if (!path.startsWith("/api/"))
                            return route.continue();
                        const pagination = { page: 1, pageSize: 200, totalItems: 0, totalPages: 1 };
                        const responses: Record<string, unknown> = {
                            "/api/auth/me": { username: "owner", role: "admin", authRequired: false },
                            "/api/setup/status": {
                                secrets: { anthropicKey: true, anyLlmKey: true },
                                profile: { documentCount: 1, hasResume: true, canRebuild: true, freshness: "current", factsBuiltAt: "2026-11-04T12:00:00Z" },
                                search: { configured: true }, sources: { enabledCount: 1 }, complete: true,
                            },
                            "/api/dashboard/summary": { statusCounts: { shortlisted: 145, approved: 2, rendered: 13 }, queues: { triage: 0, approve: 0, tailor: 0, apply: 0 }, applied: 5, sourceHealth: { openFailures: 0, affectedSources: [] } },
                            "/api/runs": { data: [], pagination }, "/api/errors": { records: [] },
                            "/api/workspace-agent/proposals": { proposals: [], nextOffset: null },
                        };
                        if (["/api/triage", "/api/shortlist", "/api/pipeline"].includes(path))
                            return route.fulfill({ json: { data: [], pagination, total: 0, facets: { source: { linkedin: 1 }, industry: { technology: 1 }, country: { US: 1 }, region: { California: 1 }, city: { "San Francisco": 1 }, companySize: { large: 1 }, skills: { TypeScript: 1 } } } });
                        return route.fulfill({ json: responses[path] ?? [] });
                    });
                    for (const destination of ["/", "/triage", "/shortlist", "/pipeline"]) {
                        await page.goto(destination);
                        const panel = destination === "/" ? page.locator("main aside") : page.locator("main section").filter({ has: page.locator("form") }).first();
                        await expect(panel).toBeVisible();
                        await page.evaluate(() => document.fonts.ready);
                        if (destination === "/") {
                            const cards = await panel.locator(':scope > [data-slot="card"]').evaluateAll(elements => elements.map(el => { const box = el.getBoundingClientRect(); return { top: box.top, bottom: box.bottom }; }));
                            expect(cards).toHaveLength(2);
                            if (Math.abs(cards[0].top - cards[1].top) < 1)
                                expect(cards[0].bottom).toBeCloseTo(cards[1].bottom, 0);
                        }
                        else {
                            const panelBox = (await panel.boundingBox())!;
                            const gridBox = (await panel.locator('[data-slot="field-group"]').boundingBox())!;
                            expect(gridBox.y - panelBox.y).toBeLessThanOrEqual(20);
                            expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
                            const fields = await panel.locator('[data-slot="field"]').evaluateAll(elements => elements.map(el => {
                                const r = el.getBoundingClientRect();
                                return { x: r.x, y: r.y, right: r.right, bottom: r.bottom };
                            }));
                            for (let i = 0; i < fields.length; i++)
                                for (let j = i + 1; j < fields.length; j++) {
                                    const a = fields[i], b = fields[j];
                                    expect(a.right <= b.x + 1 || b.right <= a.x + 1 || a.bottom <= b.y + 1 || b.bottom <= a.y + 1).toBe(true);
                                    if (Math.abs(a.y - b.y) < 2)
                                        expect(Math.abs(a.bottom - b.bottom)).toBeLessThanOrEqual(2);
                                }
                            if (width === 1440) {
                                await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
                                expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
                                await page.evaluate(() => { document.documentElement.style.fontSize = ""; });
                            }
                            await panel.locator('input[type="search"]').first().fill("Platform engineer");
                            await panel.locator('button[type="submit"]').click();
                            await expect(page).toHaveURL(/q=Platform/);
                        }
                        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
                        if (browserName === "chromium" && [390, 1440].includes(width))
                            await page.screenshot({ path: testInfo.outputPath(`${destination.slice(1) || "dashboard"}.png`), fullPage: true });
                    }
                    await page.close();
                    expect(errors).toEqual([]);
                });
            }
    });
}
