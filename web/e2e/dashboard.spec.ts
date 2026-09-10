import { expect, test } from "@playwright/test";

import { mockEmptyRuns } from "./support";

// Hermetic smoke: intercept the API so no backend is required, matching the
// pattern in e2e/smoke.spec.ts and e2e/setup-wizard.spec.ts.
test.beforeEach(async ({ page }) => {
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/errors?*", (route) => route.fulfill({ json: { records: [] } }));
  await mockEmptyRuns(page);
  await page.route("**/api/setup/status", (route) =>
    route.fulfill({
      json: {
        secrets: { anthropicKey: true, anyLlmKey: true },
        profile: { documentCount: 1, hasResume: true, factsBuiltAt: "2026-06-01T00:00:00Z", githubUsername: null },
        search: { configured: true },
        sources: { enabledCount: 1 },
        complete: true,
      },
    }));
  await page.route("**/api/dashboard/summary", (route) =>
    route.fulfill({
      json: {
        statusCounts: {
          raw: 3, extracted: 1, filtered: 2, rejected: 1,
          shortlisted: 4, approved: 1, tailored: 2, rendered: 1,
        },
        queues: { triage: 2, approve: 4, tailor: 1, apply: 1 },
        applied: 5,
      },
    }));
  await page.route("**/api/shortlist*", (route) =>
    route.fulfill({
      json: {
        data: [],
        pagination: { page: 1, pageSize: 200, totalItems: 0, totalPages: 0 },
        facets: {},
        total: 0,
      },
    }));
  await page.route("**/api/triage*", (route) =>
    route.fulfill({
      json: {
        data: [],
        pagination: { page: 1, pageSize: 200, totalItems: 0, totalPages: 0 },
        facets: {},
        total: 0,
      },
    }));
});

test("dashboard is home and queue cards deep-link", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /waiting on you/i }),
  ).toBeVisible();
  await expect(
    page.getByText("Dashboard", { exact: true }).first(),
  ).toBeVisible();
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();
  await skipLink.press("Enter");
  await expect(page.locator("main#main-content")).toBeFocused();

  await page.getByRole("link", { name: "Shortlist", exact: true }).click();
  await expect(page).toHaveURL(/\/shortlist/);

  await page.goBack();
  await page
    .getByRole("link", { name: /triage 2/i })
    .click();
  await expect(page).toHaveURL(/\/triage/);
});

test("mobile chrome keeps launch actions compact and horizontally contained", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const chrome = page.locator("header.app-chrome");
  await expect(chrome.getByText("Dashboard", { exact: true }).first()).toBeVisible();
  await expect(chrome.getByText("Command Center", { exact: true })).toHaveCount(0);

  const chromeBox = await chrome.boundingBox();
  expect(chromeBox).not.toBeNull();
  expect(chromeBox!.height).toBeLessThanOrEqual(128);

  const rail = chrome.locator(".shell-action-rail");
  const railDimensions = await rail.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(railDimensions.scrollWidth).toBeGreaterThan(railDimensions.clientWidth);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});


for (const width of [1440, 390]) {
  test(`recent runs retains operations and clears histories independently at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    let operationsCleared = false;
    let notificationsCleared = false;
    const operation = { id: 1, runId: "saved", kind: "discover", label: "Imported source documents",
      status: "succeeded", error: null, completedAt: "2026-09-09T12:00:00Z", readAt: null };
    await page.route("**/api/run-completions*", (route) => {
      if (route.request().method() === "DELETE") {
        operationsCleared = true;
        return route.fulfill({ json: { cleared: 1 } });
      }
      const notifications = new URL(route.request().url()).searchParams.get("surface") === "notifications";
      return route.fulfill({ json: (notifications ? notificationsCleared : operationsCleared) ? [] : [operation] });
    });
    await page.route("**/api/run-completions/1/logs", (route) => route.fulfill({ json: [
      { timestamp: "2026-09-09T12:00:00Z", message: "Reading source documents", state: "running" },
    ] }));
    await page.route("**/api/notifications", (route) => {
      if (route.request().method() === "DELETE") {
        notificationsCleared = true;
        return route.fulfill({ json: { cleared: 1 } });
      }
      return route.fulfill({ json: [] });
    });
    await page.goto("/");
    await expect(page.getByText("Imported source documents", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "View logs" }).click();
    await expect(page.getByText("Reading source documents")).toBeVisible();
    await page.reload();
    await expect(page.getByText("Imported source documents", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Clear operation history" }).click();
    await page.getByRole("button", { name: "Clear history", exact: true }).click();
    await expect(page.getByText("No completed operations in your history.")).toBeVisible();
    await page.getByRole("button", { name: /Notifications/ }).click();
    await expect(page.getByText("Discovery succeeded")).toBeVisible();
    await page.getByRole("button", { name: "Clear notification history" }).click();
    await page.getByRole("button", { name: "Clear history", exact: true }).click();
    await expect(page.getByText("Nothing pending.")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
