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
    await page.getByLabel("At least 18 years old", { exact: true }).fill("Yes");
    await page.getByLabel("U.S. worker category", { exact: true }).fill("No");
    await page.getByLabel("Sponsorship needed", { exact: true }).fill("U.S.: Yes, now or in the future");
    await page.getByLabel("Verification of legal right to work", { exact: true }).fill("U.S.: Yes");
    await page.getByLabel("Previous employment with each employer", { exact: true }).fill("Acme: No");
    await page.getByLabel("Export-control citizenship / dual citizenship", { exact: true }).fill("Cuba, Iran, North Korea, Syria: No");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByRole("button", { name: "Discard", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect.poll(() => profile.expectedSalary).toBe("USD 120,000/year");
    await page.reload();
    await expect(page.getByLabel("Disability status", { exact: true })).toHaveValue("Prefer not to disclose");
    await expect(page.getByLabel("U.S. worker category", { exact: true })).toHaveValue("No");
    await expect(page.getByLabel("Previous employment with each employer", { exact: true })).toHaveValue("Acme: No");
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

    await page.goto("/shortlist");
    await page.evaluate(() => {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { writeText: async () => { throw new Error("Clipboard blocked"); } },
      });
    });
    const copyButton = page.getByRole("button", { name: "Copy application prompt", exact: true });
    await copyButton.click();
    const fallback = page.getByRole("dialog");
    const promptText = fallback.getByRole("textbox", { name: "English application prompt" });
    await expect(promptText).toHaveValue(prompt);
    await expect(promptText).toBeFocused();
    expect(await promptText.evaluate((element: HTMLTextAreaElement) => element.selectionEnd - element.selectionStart)).toBe(prompt.length);
    expect(await fallback.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await expect(fallback).toHaveCSS("opacity", "1");
    await page.screenshot({ path: `test-results/application-prompt-dialog-${width}.png` });
    await page.keyboard.press("Escape");
    await expect(fallback).toHaveCount(0);
    await expect(copyButton).toBeFocused();

    await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "zh-CN"));
    await page.goto("/shortlist");
    await page.getByRole("button", { name: "复制申请提示词", exact: true }).click();
    await expect.poll(() => page.evaluate(async () => (await navigator.clipboard.readText()).replace(/\r\n/g, "\n"))).toBe(prompt);
    await page.evaluate(() => localStorage.setItem("theme", "dark"));
    await page.goto("/settings/application-profile");
    await expect(page.getByLabel("期望薪资", { exact: true })).toHaveValue("USD 120,000/year");
    await expect(page.getByLabel("是否年满18岁", { exact: true })).toHaveValue("Yes");
    await expect(page.getByLabel("出口管制所涉国籍／双重国籍", { exact: true })).toHaveValue("Cuba, Iran, North Korea, Syria: No");
    await expect(page.getByLabel("在各雇主处的任职经历", { exact: true })).toHaveValue("Acme: No");
    await expect(page.getByText("不确定的内容可以留空。自愿填写的问题，请如实回答，也可以填写“不愿透露”。留空的项目不会自动补全。", { exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveClass(/dark/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/application-profile-zh-dark-${width}.png`, fullPage: true });
    expect(errors).toEqual([]);
  });
}
