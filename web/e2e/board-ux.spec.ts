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

for (const language of ["en", "zh-CN"] as const) {
  for (const existing of [false, true]) {
    test(`job assistant recovers a ${existing ? "follow-up" : "start"} after page reload in ${language}`, async ({ page }) => {
      await page.addInitScript((selectedLanguage) => {
        localStorage.setItem("resume-tailor-harness-language", selectedLanguage);
      }, language);
      const chinese = language === "zh-CN";
      const summary = {
        sessionId: "recovered-session", title: "Job discussion", goal: "Discuss Acme",
        startedAt: "2026-10-04T12:00:00Z", endedAt: null, archivedAt: null,
        status: "active", jobId: 7, jobCompany: "Acme", jobTitle: "Staff Engineer",
      };
      const previousTurns = existing ? [
        { turnId: "old-user", role: "user", text: "Earlier question" },
        { turnId: "old-assistant", role: "assistant", text: "Earlier answer" },
      ] : [];
      let launched = false;
      let saved = false;
      const run = () => ({
        runId: "recovered-run", kind: "career-lab-turn", state: saved ? "done" : "running",
        percent: saved ? 100 : 20, label: saved ? "Done" : "Drafting", current: 1, total: 2,
        meta: { jobId: 7, turnCount: previousTurns.length, ...(existing ? { sessionId: summary.sessionId } : {}) },
        result: saved ? { sessionId: summary.sessionId } : null, error: null,
      });
      await page.route("**/api/jobs/7", (route) => route.fulfill({ json: {
        id: 7, source: "greenhouse", company: "Acme", title: "Staff Engineer",
        location: "Remote", jdText: "Build platform services.", status: "shortlisted",
        fitScore: 88, skills: [], resumeVersions: [], coverLetters: [], application: null,
      } }));
      await page.route("**/api/transcribe/availability", (route) => route.fulfill({ json: { available: false } }));
      await page.route("**/api/auth/link-token", (route) => route.fulfill({ json: { token: "fixture-link", expiresInSeconds: 60 } }));
      await page.route("**/api/runs/ack", (route) => route.fulfill({ json: { acknowledged: 1 } }));
      await page.route("**/api/runs?*", (route) => route.fulfill({ json: {
        data: launched ? [run()] : [], pagination: { page: 1, pageSize: 200, totalItems: launched ? 1 : 0, totalPages: 1 },
      } }));
      await page.route("**/api/runs/recovered-run", (route) => route.fulfill({ json: run() }));
      await page.route("**/api/runs/recovered-run/events*", (route) => route.fulfill({
        contentType: "text/event-stream", body: `data: ${JSON.stringify(run())}\n\n`,
      }));
      await page.route("**/api/runs/recovered-run/stream?*", (route) => route.fulfill({
        contentType: "text/event-stream", body: [
          { i: 0, t: "text", v: { text: "Draft before reload" } },
          { i: 1, t: "settled", v: {} },
        ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""),
      }));
      await page.route("**/api/career-lab/sessions?*", (route) => {
        const sessions = existing || saved ? [{ ...summary, turnCount: previousTurns.length + (saved ? 2 : 0) }] : [];
        return route.fulfill({ json: { sessions, activeSessions: sessions, pagination: { page: 1, pageSize: 20, totalItems: sessions.length, totalPages: 1 } } });
      });
      await page.route("**/api/career-lab/sessions/recovered-session", (route) => route.fulfill({ json: {
        ...summary, turns: saved ? [...previousTurns,
          { turnId: "new-user", role: "user", text: "Question before reload" },
          { turnId: "new-assistant", role: "assistant", text: "Saved answer after reload" },
        ] : previousTurns,
      } }));
      await page.route(existing ? "**/api/career-lab/sessions/recovered-session/messages" : "**/api/career-lab/sessions", (route) => {
        launched = true;
        return route.fulfill({ status: 202, json: run() });
      });

      await page.goto("/shortlist?job=7");
      const openAssistant = () => page.getByRole("button", { name: chinese ? "咨询此职位" : "Ask about this job", exact: true }).click();
      await openAssistant();
      const panel = page.getByRole("dialog", { name: chinese ? "职业助手" : "Career assistant" });
      const composer = panel.getByRole("textbox", { name: chinese ? "咨询此职位" : "Ask about this job" });
      await composer.fill("Question before reload");
      await composer.press("Enter");
      await expect(panel.getByText("Draft before reload")).toBeVisible();

      // This destroys the mutation callback and the in-memory query cache.
      await page.reload();
      await openAssistant();
      await expect(panel.getByText("Draft before reload")).toBeVisible();
      if (existing) await expect(panel.getByText("Earlier answer")).toBeVisible();
      else await expect(panel.getByRole("link")).toHaveCount(0);
      saved = true;

      await expect(panel.getByText("Saved answer after reload")).toBeVisible({ timeout: 20_000 });
      await expect(panel.getByText("Question before reload")).toBeVisible();
      await expect(panel.getByText("Draft before reload")).toHaveCount(0);
      await expect(panel.getByRole("link", { name: chinese ? "打开完整工作区" : "Open full workspace" })).toHaveAttribute("href", "/career-lab?session=recovered-session");
      await expect(composer).toBeEnabled();
      await expect(panel.getByRole("alert")).toHaveCount(0);
    });
  }
}
