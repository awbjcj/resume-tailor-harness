import { expect, test, type Page } from "@playwright/test";
import { mockEmptyRuns } from "./support";

const review = {
  maxRounds: 3, scoreThreshold: 85, mergedAdvisory: true, evidencePortfolioEnabled: false,
  earlyStopOnRegression: false, tailorTier: "premium", reviserTier: "premium", provenanceRetryBudget: 1,
  styleGuidePath: "config/style_guide.md",
  reviewers: [{ name: "fact-check", gate: true, weight: 0, modelTier: "premium", scoreBands: false }],
  lengthBudget: { pageTarget: 2, maxExperiences: 5, maxProjects: 4, maxEvidenceOwners: 8,
    minBulletsPerRole: 5, maxBulletsPerRole: 7, minBulletsPerProject: 4, maxBulletsPerProject: 6,
    targetTotalBullets: 40, minAspectsPerOwner: 3, targetSkills: 40, maxSkillsPerCategory: 12 },
};

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    localStorage.setItem("resume-tailor-harness-language", "en");
    localStorage.setItem("theme", "light");
  });
  await mockEmptyRuns(page);
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: { complete: true } }));
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/config/review", (route) => route.fulfill({ json: review }));
  let search = { keywords: ["platform"], titles: ["Software Engineer"], locations: ["Remote"], remotePolicy: ["remote"], minSalary: null };
  await page.route("**/api/config/search", (route) => {
    if (route.request().method() === "PUT") search = route.request().postDataJSON();
    return route.fulfill({ json: search });
  });
  await page.route("**/api/config/application-profile", (route) => route.fulfill({ json: { fullName: "Example Applicant" } }));
  await page.route("**/api/config/models", (route) => route.fulfill({ json: {
    cheapModel: "openai:test", midModel: "openai:test", premiumModel: "openai:test",
    cheapReasoningEffort: null, midReasoningEffort: null, premiumReasoningEffort: null,
  } }));
  await page.route("**/api/config/models/catalog", (route) => route.fulfill({ json: [] }));
});

async function goToReview(page: Page, width: number) {
  const nav = page.getByRole("navigation", { name: "Settings", exact: true });
  if (width >= 1024) await nav.getByRole("link", { name: "Review panel", exact: true }).click();
  else await nav.getByRole("combobox", { name: "Settings section" }).selectOption("/settings/review");
}

for (const width of [375, 768, 1024, 1440]) {
  test(`protects drafts during section switching at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/settings/search");
    if (width === 1440) {
      await expect(page.getByLabel("Keywords", { exact: true })).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath("search.png"), fullPage: true });
    }
    await page.getByLabel("Keywords", { exact: true }).fill("distributed systems");
    // Even text not yet added as a tag is an unsaved edit.
    await goToReview(page, width);
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.getByRole("button", { name: "Keep editing", exact: true }).click();
    await expect(page.getByLabel("Keywords", { exact: true })).toHaveValue("distributed systems");
    await page.getByLabel("Keywords", { exact: true }).press("Enter");
    await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeInViewport();
    await page.screenshot({ path: testInfo.outputPath("search-dirty.png"), fullPage: true });
    await goToReview(page, width);
    await page.getByRole("button", { name: "Discard and leave", exact: true }).click();
    await expect(page.getByLabel("Max rounds", { exact: true })).toBeVisible();
    const table = page.getByRole("region", { name: "Reviewer settings table" });
    await table.focus();
    await expect(table).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("review.png"), fullPage: true });
  });
}

test("successful saves clear the navigation guard", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/settings/search");
  await page.getByLabel("Minimum salary", { exact: true }).fill("120000");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toHaveCount(0);
  await goToReview(page, 1440);
  await expect(page.getByLabel("Max rounds", { exact: true })).toBeVisible();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
});

test("reveals required fields in collapsed application sections before validation", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/settings/application-profile");
  await expect(page.getByLabel("Full name", { exact: true })).toHaveValue("Example Applicant");
  const section = page.locator("details").filter({ has: page.getByRole("heading", { name: "Alternate application emails", exact: true }) });
  await section.locator("summary").click();
  await page.getByRole("button", { name: "Add alternate email", exact: true }).click();
  await section.locator("summary").click();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(section).toHaveAttribute("open", "");
  await expect(page.getByLabel("Alternate email", { exact: false }).first()).toBeFocused();
  await page.getByRole("button", { name: "Discard", exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove alternate email", exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("application-profile.png"), fullPage: true });
});

test("keeps the API key editor available after a failed save", async ({ page }) => {
  let attempts = 0;
  const statuses = [{ key: "openaiApiKey", isSet: false, hint: null }];
  await page.route("**/api/secrets", (route) => {
    if (route.request().method() === "PUT" && ++attempts === 1) {
      return route.fulfill({ status: 503, json: { error: { message: "Service unavailable" } } });
    }
    return route.fulfill({ json: statuses });
  });
  await page.goto("/settings/keys");
  await page.getByRole("button", { name: "Add OpenAI API key", exact: true }).click();
  const input = page.getByLabel("OpenAI API key new value", { exact: true });
  await input.fill("test-only-key");
  await page.getByRole("button", { name: "Save key", exact: true }).click();
  await expect(input).toHaveValue("test-only-key");
  await expect(page.getByRole("alert")).toContainText("Service unavailable");
  await page.getByRole("button", { name: "Save key", exact: true }).click();
  await expect(input).toHaveCount(0);
});

test("loads job launch forms on demand and preserves their draft when closed", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route("**/api/triage?*", (route) => route.fulfill({ json: {
    data: [], pagination: { page: 1, pageSize: 200, totalItems: 0, totalPages: 1 }, facets: {}, total: 0,
  } }));
  await page.goto("/triage");
  await page.getByRole("button", { name: "Pull", exact: true }).click();
  const limit = page.getByLabel("Limit per connector (optional)", { exact: true });
  await limit.fill("5");
  await limit.press("Escape");
  await page.getByRole("button", { name: "Pull", exact: true }).click();
  await expect(limit).toHaveValue("5");
  await limit.press("Escape");
  await page.getByRole("button", { name: "Reprocess", exact: true }).click();
  await page.getByRole("combobox", { name: "Scope", exact: true }).click();
  await page.getByRole("option", { name: "Reconsider off-target", exact: true }).click();
  await page.getByRole("combobox", { name: "Scope", exact: true }).press("Escape");
  await page.getByRole("button", { name: "Reprocess", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Scope", exact: true })).toContainText("Reconsider off-target");
});
