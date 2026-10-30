import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";

for (const language of ["en", "zh-CN"] as const) {
  for (const width of [375, 1440]) {
    test(`browser can fill every manual job field: ${language}, ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((language) => localStorage.setItem("resume-tailor-harness-language", language), language);
      await mockEmptyRuns(page);
      await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/board-views*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
      await page.route("**/api/triage*", (route) => route.fulfill({ json: {
        data: [], total: 0, facets: {}, pagination: { page: 1, pageSize: 50, totalItems: 0, totalPages: 1 },
      } }));
      let posted: Record<string, unknown> | undefined;
      await page.route("**/api/jobs", async (route) => {
        posted = route.request().postDataJSON();
        await route.fulfill({ status: 201, json: { id: 42, title: "Platform Engineer", company: "Acme" } });
      });
      await page.goto("/triage");
      const zh = language === "zh-CN";
      await page.getByRole("button", { name: zh ? "手动添加职位" : "Add job manually", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("heading", { name: zh ? "手动添加职位" : "Add job manually" })).toBeVisible();
      await expect(dialog.getByLabel(zh ? "职位名称 *" : "Job title *", { exact: true })).toHaveAttribute("required", "");
      for (const [name, value] of Object.entries({
        title: "Platform Engineer", company: "Acme", jdText: "Build reliable Python services.\nOwn distributed systems.",
        location: "Boston, MA; New York, NY", url: "https://example.com/jobs/42", applicationUrl: "https://apply.example.com/42",
        postingId: "REQ-42", postedAt: "2026-10-01", closesAt: "2026-11-30",
        remoteRestrictions: "United States", attendance: "Two days per week", industry: "Software",
        companySize: "201-500", yoeMin: "5", techStack: "Python\nSQL", mustHaveSkills: "Distributed systems",
        niceToHaveSkills: "Kubernetes", salaryMin: "120000", salaryMax: "160000", salaryCurrency: "USD",
      })) await dialog.locator(`[name="${name}"]`).fill(value);
      for (const [name, value] of Object.entries({
        remotePolicy: "hybrid", employmentType: "full_time", seniority: "senior", sponsorshipSignal: "offered", salaryPeriod: "year",
      })) await dialog.locator(`[name="${name}"]`).selectOption(value);
      const box = await dialog.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      await dialog.getByRole("button", { name: zh ? "保存职位" : "Save job", exact: true }).click();
      await expect(dialog.getByRole("status")).toContainText("42");
      expect(posted).toEqual({
        title: "Platform Engineer", company: "Acme", jdText: "Build reliable Python services.\nOwn distributed systems.",
        location: "Boston, MA; New York, NY", url: "https://example.com/jobs/42", postedAt: "2026-10-01T00:00:00Z",
        details: {
          applicationUrl: "https://apply.example.com/42", postingId: "REQ-42", closesAt: "2026-11-30",
          remotePolicy: "hybrid", employmentType: "full_time", seniority: "senior", sponsorshipSignal: "offered",
          remoteRestrictions: "United States", attendance: "Two days per week", industry: "Software", companySize: "201-500",
          yoeMin: 5, techStack: ["Python", "SQL"], mustHaveSkills: ["Distributed systems"], niceToHaveSkills: ["Kubernetes"],
          salaryMin: 120000, salaryMax: 160000, salaryCurrency: "USD", salaryPeriod: "year",
        },
      });
      await expect(dialog.getByRole("link", { name: zh ? "查看已保存的职位" : "View saved job" })).toHaveAttribute("href", "/triage?job=42");
    });
  }
}
