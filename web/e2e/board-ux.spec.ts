import { expect, test } from "@playwright/test";

import { mockEmptyRuns } from "./support";

test.beforeEach(async ({ page }) => {
  await mockEmptyRuns(page);
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/setup/status", (route) =>
    route.fulfill({
      json: {
        secrets: { anthropicKey: true, anyLlmKey: true },
        profile: {
          documentCount: 1,
          hasResume: true,
          factsBuiltAt: "2026-07-13T00:00:00Z",
          githubUsername: null,
        },
        search: { configured: true },
        sources: { enabledCount: 1 },
        complete: true,
      },
    }),
  );
  await page.route("**/api/shortlist*", (route) =>
    route.fulfill({
      json: {
        data: [
          {
            jobId: 7,
            company: "Acme",
            title: "Staff Engineer",
            location: "Remote",
            fitScore: 88,
            url: "https://jobs.example.test/7",
            skills: [],
          },
        ],
        pagination: { page: 1, pageSize: 200, totalItems: 1, totalPages: 1 },
        facets: {},
        total: 1,
      },
    }),
  );
});

test("switches board view, exposes quick actions, and opens import", async ({ page }) => {
  let archived: boolean | undefined;
  await page.route("**/api/jobs/7", async (route) => {
    if (route.request().method() === "PATCH") {
      archived = (route.request().postDataJSON() as { archived?: boolean }).archived;
      await route.fulfill({ json: {} });
      return;
    }
    await route.fallback();
  });

  await page.goto("/shortlist");
  await page.getByRole("button", { name: "List view" }).click();

  await expect(page).toHaveURL(/view=list/);
  await expect(page.getByRole("link", { name: "Open posting" })).toHaveAttribute(
    "href",
    "https://jobs.example.test/7",
  );
  await page.getByRole("button", { name: "Archive job" }).click();
  await expect.poll(() => archived).toBe(true);

  await page.getByRole("button", { name: /import file/i }).click();
  await expect(page.getByRole("heading", { name: "Import jobs" })).toBeVisible();
  await expect(page.getByLabel("Import file")).toHaveAttribute(
    "accept",
    ".csv,.json,.txt",
  );
});

test("job assistant sends explicit context and displays an AG-UI response", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.route("**/api/jobs/7", (route) => route.fulfill({ json: {
    id: 7, source: "greenhouse", company: "Acme", title: "Staff Engineer", url: "https://jobs.example.test/7", location: "Remote", jdText: "Build platform services.", status: "shortlisted", fitScore: 88, skills: [], resumeVersions: [{ id: 3, round: 1, origin: "tailor" }], coverLetters: [], application: null,
  } }));
  await page.route("**/api/transcribe/availability", (route) => route.fulfill({ json: { available: false } }));
  await page.route("**/api/career-lab/sessions?*", (route) => route.fulfill({ json: { sessions: [], activeSessions: [], pagination: { page: 1, pageSize: 20, totalItems: 0, totalPages: 1 } } }));
  await page.route("**/api/auth/link-token", (route) => route.fulfill({ json: { token: "fixture-link", expiresInSeconds: 60 } }));
  let context: unknown;
  await page.route("**/api/career-lab/sessions", async (route) => {
    context = route.request().postDataJSON().context;
    await route.fulfill({ status: 202, json: { runId: "assistant-run", kind: "career-lab-turn", status: "running", percent: 0, label: "Drafting", meta: { jobId: 7 } } });
  });
  await page.route("**/api/runs/assistant-run/events*", (route) => route.fulfill({ contentType: "text/event-stream", body: 'data: {"status":"running","label":"Drafting","percent":0}\n\n' }));
  await page.route("**/api/runs/assistant-run", (route) => route.fulfill({ json: { runId: "assistant-run", kind: "career-lab-turn", status: "running", percent: 0, label: "Drafting" } }));
  await page.route("**/api/runs/assistant-run/stream?*", (route) => route.fulfill({ contentType: "text/event-stream", body: [
    { type: "RUN_STARTED", runId: "assistant-run", threadId: "s" },
    { type: "TEXT_MESSAGE_CHUNK", role: "assistant", messageId: "m", delta: "Focus on the platform requirements.", rawEvent: { index: 0 } },
    { type: "CUSTOM", name: "resume.settled", value: {}, rawEvent: { index: 1 } },
  ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join("") }));
  await page.goto("/shortlist");
  await page.getByText("Staff Engineer", { exact: true }).click();
  const masthead = page.getByRole("dialog").locator("header");
  for (const action of [masthead.getByRole("button", { name: "Ask about this job", exact: true }), masthead.getByRole("button", { name: "Redo…", exact: true }), masthead.getByRole("button", { name: "Draft email", exact: true }), masthead.getByRole("link", { name: "Open posting" })]) {
    await expect(action).toBeInViewport({ ratio: 1 });
    await action.click({ trial: true });
  }
  await page.getByRole("button", { name: "Ask about this job", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Career assistant" });
  await panel.getByText("Context: this job", { exact: true }).click();
  await panel.getByLabel("Resume version", { exact: true }).selectOption("3");
  await panel.getByRole("checkbox", { name: "Include current profile" }).check();
  await panel.getByRole("textbox", { name: "Ask about this job" }).fill("Which requirements should I address?");
  await panel.getByRole("button", { name: "Send message" }).click();
  await expect(panel.getByText("Focus on the platform requirements.")).toBeVisible();
  expect(context).toEqual({ jobId: 7, resumeVersionId: 3, profileSnapshot: "current", offerApplicationIds: [] });
  await expect(panel.getByText("Saving the response", { exact: true })).toBeVisible();
  await page.screenshot({ path: "e2e/__screenshots__/agui-job-assistant.png" });
});
