import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";

for (const width of [1280, 390]) {
  test(`application profile and English prompt at ${width}px`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 900 });
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "en"));
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await mockEmptyRuns(page);
    await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
    await page.route("**/api/notifications*", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/board-views*", (route) => route.fulfill({ json: [] }));
    let profile: Record<string, string> = { fullName: "Ada", expectedSalary: "", disabilityStatus: "" };
    await page.route("**/api/config/application-profile", async (route) => {
      if (route.request().method() === "PUT") profile = route.request().postDataJSON();
      await route.fulfill({ json: profile });
    });
    await page.route("**/api/shortlist*", (route) => route.fulfill({ json: {
      data: [{ jobId: 7, company: "Acme", title: "Staff Engineer", location: "Remote", fitScore: 88, url: "https://example.com/apply/7", skills: [] }],
      pagination: { page: 1, pageSize: 200, totalItems: 1, totalPages: 1 }, facets: {}, total: 1,
    } }));
    const prompt = "# Fill in my job application using the live browser\nJob: Staff Engineer at Acme\nApplicant: Ada";
    await page.route("**/api/jobs/7/application-prompt", (route) => route.fulfill({ json: { prompt } }));
    await page.route("**/api/jobs/7", (route) => route.fulfill({ json: {
      id: 7, source: "manual", company: "Acme", title: "Staff Engineer", location: "Remote", url: "https://example.com/apply/7", jdText: "Build services", status: "shortlisted", fitScore: 88, skills: [], resumeVersions: [], coverLetters: [], application: null,
    } }));

    await page.goto("/settings/application-profile");
    await expect(page.getByRole("heading", { name: "Application profile", exact: true })).toBeVisible();
    await page.getByLabel("Expected salary", { exact: true }).fill("USD 120,000/year");
    await page.getByLabel("Disability status", { exact: true }).fill("Prefer not to disclose");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect.poll(() => profile.expectedSalary).toBe("USD 120,000/year");
    await page.reload();
    await expect(page.getByLabel("Disability status", { exact: true })).toHaveValue("Prefer not to disclose");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/application-profile-${width}.png`, fullPage: true });

    await page.goto("/shortlist");
    await page.getByRole("button", { name: "Copy application prompt", exact: true }).click();
    await expect.poll(() => page.evaluate(async () => (await navigator.clipboard.readText()).replace(/\r\n/g, "\n"))).toBe(prompt);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByText("Staff Engineer", { exact: true }).click();
    await expect(page.getByRole("dialog").getByRole("button", { name: "Copy application prompt", exact: true })).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: "Copy application prompt", exact: true }).click();
    await expect.poll(() => page.evaluate(async () => (await navigator.clipboard.readText()).replace(/\r\n/g, "\n"))).toBe(prompt);

    await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "zh-CN"));
    await page.goto("/shortlist");
    await page.getByRole("button", { name: "复制申请提示词", exact: true }).click();
    await expect.poll(() => page.evaluate(async () => (await navigator.clipboard.readText()).replace(/\r\n/g, "\n"))).toBe(prompt);
    expect(errors).toEqual([]);
  });
}
