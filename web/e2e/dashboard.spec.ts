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
        activeCoachSession: { sessionId: "c1", savedNoteCount: 0, startedAt: "2026-09-09T12:00:00Z" },
        sourceHealth: { openFailures: 0, affectedSources: [], latestFailureAt: null },
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

test("dashboard handles application decisions and follow-ups while the bell stays informational", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const base = {
    applicationId: 1, jobId: 7, company: "Acme", title: "Staff Engineer",
    createdAt: "2026-10-23T12:00:00Z", state: "pending", revision: "r1",
  };
  let pending = [
    { ...base, id: 1, kind: "interview", proposedStatus: "interview", evidence: "Can we schedule a call?", messageId: "email-1" },
    { ...base, id: 2, kind: "rejected", proposedStatus: "rejected", evidence: "Thanks for your interest.", messageId: "email-2" },
    { ...base, id: 3, kind: "follow_up", proposedStatus: "", evidence: "No activity for 20 days: Acme · Staff Engineer", messageId: "follow-up" },
    { ...base, id: 4, kind: "offer_deadline_soon", proposedStatus: "", evidence: "Offer deadline Oct 24, 18:00 UTC: Acme · Staff Engineer", messageId: "reminder" },
  ];
  const decisions: string[] = [];
  await page.route("**/api/notifications", (route) => route.fulfill({ json: pending }));
  await page.route(/\/api\/notifications\/\d+\/(accept|dismiss)$/, (route) => {
    const [, id, action] = /\/(\d+)\/(accept|dismiss)$/.exec(route.request().url())!;
    const item = pending.find((entry) => entry.id === Number(id));
    decisions.push(`${id}/${action}`);
    if (id === "3" && decisions.filter((decision) => decision === "3/accept").length === 1) {
      return route.fulfill({ status: 500, json: { error: { code: "TEST_ERROR", message: "Try again" } } });
    }
    pending = pending.filter((entry) => entry !== item);
    return route.fulfill({ json: item });
  });
  await page.route("**/api/jobs/7/email-drafts", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [{
    id: 11, runId: "saved", kind: "discover", label: "Imported source documents", status: "succeeded",
    error: null, completedAt: "2026-10-23T12:00:00Z", readAt: null,
  }] }));

  await page.goto("/");
  const board = page.getByRole("region", { name: "Application notifications" });
  const bell = page.getByRole("button", { name: "Notifications (2 pending)" });
  await expect(board.getByText("Can we schedule a call?")).toBeVisible();
  await expect(board.getByRole("link", { name: "View job" })).toHaveAttribute("href", "/pipeline?job=7");
  await expect(page.getByRole("region", { name: "Recent runs" }).getByText("Imported source documents")).toBeVisible();
  await bell.click();
  const popover = page.getByRole("dialog", { name: "Notifications" });
  await expect(popover.getByText("Offer deadline: Acme")).toBeVisible();
  await expect(popover.getByText("Discovery succeeded")).toBeVisible();
  await expect(popover.getByText("Can we schedule a call?")).toHaveCount(0);
  await expect(popover.getByText("Follow up: Acme")).toHaveCount(0);
  await expect(popover.getByRole("button", { name: /approve|reject update|draft follow-up|sync gmail/i })).toHaveCount(0);
  await page.keyboard.press("Escape");

  const interview = board.getByRole("listitem").filter({ hasText: "Can we schedule a call?" });
  await interview.getByRole("button", { name: "Add to timeline" }).click();
  const review = page.getByRole("dialog", { name: "Review application update" });
  await expect(review.getByRole("checkbox", { name: /confirmed the stage and date/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(review).toBeHidden();
  const approve = interview.getByRole("button", { name: "Approve update", exact: true });
  expect((await approve.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await approve.press("Enter");
  await expect(interview).toHaveCount(0);
  await expect(board.getByRole("heading", { name: "Application notifications" })).toBeFocused();
  const rejection = board.getByRole("listitem").filter({ hasText: "Thanks for your interest." });
  await rejection.getByRole("button", { name: "Dismiss update" }).click();
  await expect(rejection).toHaveCount(0);
  const draft = board.getByRole("button", { name: "Draft follow-up" });
  await draft.click();
  await expect(board.getByRole("alert")).toHaveText("Could not save your decision. Try again.");
  await draft.click();
  await expect(page.getByRole("dialog", { name: "Draft email" }).getByRole("button", { name: "Follow-up", pressed: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(draft).toHaveCount(0);
  expect(decisions).toEqual(["1/accept", "2/dismiss", "3/accept", "3/accept"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("mobile chrome keeps launch actions compact and horizontally contained", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const chrome = page.locator("header.app-chrome");
  await expect(chrome.getByText("Dashboard", { exact: true })).toHaveCount(0);
  await expect(chrome.getByRole("button", { name: "Toggle Sidebar" })).toBeVisible();
  await expect(page.getByRole("main")).toHaveCount(1);
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

test("several recent runs use the full dashboard width beneath status", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/run-completions?*surface=operations*", (route) => route.fulfill({
    json: Array.from({ length: 4 }, (_, index) => ({
      id: index + 1, runId: `run-${index}`, kind: "mailboxSync", label: "Analyzed 0 emails",
      status: "succeeded", completedAt: "2026-09-09T12:00:00Z", readAt: null,
      resultHref: "/applications", resultAvailable: false,
    })),
  }));
  await page.goto("/");
  const status = page.getByRole("complementary", { name: "System status" });
  const recentRuns = page.getByRole("region", { name: "Recent runs" });
  await expect(status.getByText("All sources are healthy.")).toBeVisible();
  await expect(recentRuns.getByRole("button", { name: "View logs" })).toHaveCount(4);

  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const [pipelineBox, statusBox, runsBox] = await Promise.all([
      page.getByLabel("Pipeline stages").boundingBox(), status.boundingBox(), recentRuns.boundingBox(),
    ]);
    expect(runsBox!.width).toBeCloseTo(pipelineBox!.width, 0);
    expect(runsBox!.y).toBeGreaterThanOrEqual(statusBox!.y + statusBox!.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  }
});

for (const language of ["en", "zh-CN"] as const) {
  test(`operation logs preserve progress and diagnostics in ${language}`, async ({ page }) => {
    await page.addInitScript((selectedLanguage) => {
      localStorage.setItem("resume-tailor-harness-language", selectedLanguage);
    }, language);
    const operation = { id: 1, runId: "saved", kind: "career-lab-turn", label: "Draft is ready",
      status: "succeeded", error: null, completedAt: "2026-09-09T12:00:00Z", readAt: null };
    await page.route("**/api/run-completions?*", (route) => route.fulfill({ json:
      new URL(route.request().url()).searchParams.get("surface") === "operations" ? [operation] : [],
    }));
    await page.route("**/api/run-completions/1/logs", (route) => route.fulfill({ json: [
      { timestamp: operation.completedAt, message: "Drafting your Career Lab response", state: "running" },
      { timestamp: operation.completedAt, message: "Draft is ready", state: "done" },
      { timestamp: operation.completedAt, message: "Saved 2 turns in career-1", state: "done" },
      { timestamp: operation.completedAt, message: "Provider timeout after 30s", state: "error" },
    ] }));
    await page.goto("/");
    await page.getByRole("button", { name: language === "en" ? "View logs" : "查看日志" }).click();
    const logs = page.locator("#operation-logs-1");
    await expect(logs).toContainText(language === "en" ? "Drafting your Career Lab response" : "正在起草职业实验室回复");
    await expect(logs).toContainText(language === "en" ? "Draft is ready" : "草稿已完成");
    await expect(logs).toContainText("Saved 2 turns in career-1");
    await expect(logs).toContainText("Provider timeout after 30s");
    await expect(logs).not.toContainText("操作失败。请重试。");
  });
}


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
    await page.getByRole("button", { name: "Clear run history", exact: true }).click();
    await page.getByRole("button", { name: "Clear history", exact: true }).click();
    await expect(page.getByText("Nothing pending.")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
