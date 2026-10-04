import { expect, test, type Page, type Route } from "@playwright/test";

const activeCareerLab = {
  sessionId: "career-1", title: "Offer strategy", goal: "Compare two offers", startedAt: "2026-08-02T12:00:00Z", endedAt: null, status: "active", archivedAt: null, turnCount: 1,
};

async function mockCareerLab(page: Page, active = false) {
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { username: null, role: null, authRequired: false } }));
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/transcribe/availability", (route) => route.fulfill({ json: { available: false } }));
  await page.route("**/api/runs?*", (route) => route.fulfill({ json: { data: [], pagination: { page: 1, pageSize: 200, totalItems: 0, totalPages: 0 } } }));
  await page.route("**/api/interview/sessions", (route) => route.fulfill({ json: { sessions: [] } }));
  await page.route("**/api/interview/sessions?*", (route) => route.fulfill({ json: { sessions: [] } }));
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: { secrets: { anthropicKey: true, anyLlmKey: true }, profile: { documentCount: 1, hasResume: true, factsBuiltAt: "2026-08-01T00:00:00Z", githubUsername: null }, search: { configured: true }, sources: { enabledCount: 1 }, complete: true } }));
  await page.route("**/api/career-lab/skills", (route) => route.fulfill({ json: { skills: [{ name: "salary-negotiation-prep", description: "Prepare negotiation points.", family: "career_lab", uses: ["career_lab"], isAvailable: true, unavailableReason: null }] } }));
  await page.route("**/api/career-lab/sessions?*", (route) => route.fulfill({ json: { sessions: active ? [activeCareerLab] : [], pagination: { page: 1, pageSize: 20, totalItems: active ? 1 : 0, totalPages: 1 } } }));
  if (active) {
    await page.route("**/api/career-lab/sessions/career-1", (route) => route.fulfill({ json: { ...activeCareerLab, turns: [] } }));
  }
  await page.route("**/api/pipeline?*", (route) => route.fulfill({ json: {
    data: [
      { jobId: 7, company: "Acme", title: "Staff Engineer", source: "linkedin", location: "New York", status: "tailored", fitScore: 91, jdPreview: "", critiqueJson: null, pdfPath: null, applicationStatus: null, salaryMin: null, salaryMax: null, hasProgress: true },
      { jobId: 8, company: "Globex", title: "Product Lead", source: "indeed", location: "Remote", status: "applied", fitScore: 84, jdPreview: "", critiqueJson: null, pdfPath: null, applicationStatus: "submitted", salaryMin: null, salaryMax: null, hasProgress: true },
    ],
    pagination: { page: 1, pageSize: 200, totalItems: 2, totalPages: 1 },
    facets: {},
    total: 2,
  } }));
  await page.route("**/api/jobs/7", (route) => route.fulfill({ json: { id: 7, resumeVersions: [] } }));
}

test.beforeEach(async ({ page }) => { await mockCareerLab(page); });

for (const language of ["en", "zh-CN"] as const) {
  test(`successful Career Lab conversations stay successful in ${language}`, async ({ page }) => {
    await page.addInitScript((selectedLanguage) => {
      localStorage.setItem("resume-tailor-harness-language", selectedLanguage);
    }, language);
    const chinese = language === "zh-CN";
    const turns: { turnId: string; role: string; text: string; at: string }[] = [];
    const runs = new Map<string, Record<string, unknown>>();
    await page.route("**/api/auth/link-token", (route) => route.fulfill({ json: { token: "fixture-link", expiresInSeconds: 60 } }));
    await page.route("**/api/runs/ack", (route) => route.fulfill({ json: { acknowledged: 1 } }));
    await page.route("**/api/career-lab/sessions?*", (route) => route.fulfill({ json: {
      sessions: turns.length ? [activeCareerLab] : [],
      activeSessions: turns.length ? [activeCareerLab] : [],
      pagination: { page: 1, pageSize: 20, totalItems: turns.length ? 1 : 0, totalPages: 1 },
    } }));
    await page.route("**/api/career-lab/sessions/career-1", (route) => route.fulfill({ json: { ...activeCareerLab, turns } }));
    const launch = async (route: Route) => {
      const message = route.request().postDataJSON().message as string;
      const runId = `career-success-${runs.size + 1}`;
      turns.push(
        { turnId: `${runId}-user`, role: "user", text: message, at: "2026-10-04T12:00:00Z" },
        { turnId: `${runId}-assistant`, role: "assistant", text: `Saved response ${runs.size + 1}`, at: "2026-10-04T12:00:01Z" },
      );
      const run = { runId, kind: "career-lab-turn", state: "done", percent: 100, current: 1, total: 1, label: "Done", result: { sessionId: "career-1" }, error: null };
      runs.set(runId, run);
      await route.fulfill({ status: 202, json: { ...run, state: "pending", percent: 0, result: null } });
    };
    await page.route("**/api/career-lab/sessions", launch);
    await page.route("**/api/career-lab/sessions/career-1/messages", launch);
    await page.route("**/api/runs/career-success-*", async (route) => {
      const runId = new URL(route.request().url()).pathname.split("/")[3];
      await route.fulfill({ json: runs.get(runId) });
    });
    await page.route("**/api/runs/career-success-*/events*", async (route) => {
      const runId = new URL(route.request().url()).pathname.split("/")[3];
      await route.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify(runs.get(runId))}\n\n` });
    });
    await page.route("**/api/runs/career-success-*/stream?*", (route) => route.fulfill({ contentType: "text/event-stream", body: 'data: {"i":0,"t":"completed","v":{}}\n\n' }));

    await page.goto("/career-lab");
    await page.getByRole("button", { name: chinese ? "创建职业实验室会话" : "Create Career Lab session", exact: true }).click();
    await page.getByRole("textbox", { name: chinese ? "职业实验室请求" : "Career Lab request" }).fill("Help me plan my next step");
    await page.getByRole("button", { name: chinese ? "开始会话" : "Start session", exact: true }).click();
    await expect(page.getByText("Saved response 1", { exact: true })).toBeVisible();
    const composer = page.getByRole("textbox", { name: chinese ? "给职业实验室发消息" : "Message Career Lab" });
    await expect(composer).toHaveValue("");
    await expect(composer).toBeEnabled();
    await composer.fill("Make the plan concise");
    await composer.press("Enter");
    await expect(page.getByText("Saved response 2", { exact: true })).toBeVisible();
    await expect(composer).toHaveValue("");
    await expect(composer).toBeEnabled();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page.getByText("职业实验室任务未完成", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Career Lab run did not complete", { exact: true })).toHaveCount(0);
  });
}

test("draft workspace preserves versions and prepares feedback with an explicit reference", async ({ page }) => {
  await page.unrouteAll();
  await mockCareerLab(page, true);
  await page.route("**/api/career-lab/sessions/career-1", (route) => route.fulfill({ json: {
    ...activeCareerLab,
    turns: [
      { turnId: "u1", role: "user", text: "Make a plan", at: "2026-10-04T12:00:00Z", contextRefs: { profileSnapshot: "current", offerApplicationIds: [] } },
      { turnId: "draft-1", role: "assistant", text: "## Experience\nFirst version", at: "2026-10-04T12:00:01Z", artifact: { title: "First plan", summary: "Plan", artifactType: "career_plan" } },
      { turnId: "draft-2", role: "assistant", text: "## Next steps\nSecond version", at: "2026-10-04T12:00:02Z", artifact: { title: "Revised plan", summary: "Plan", artifactType: "career_plan" } },
    ],
  } }));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/career-lab");
  await expect(page.getByLabel("Draft content")).toContainText("Second version");
  await page.getByLabel("Draft version").selectOption("draft-1");
  await expect(page.getByLabel("Draft content")).toContainText("First version");
  await page.getByLabel("Revision scope").selectOption("Experience");
  await page.getByLabel("Feedback", { exact: true }).fill("Keep only supported achievements");
  await page.getByRole("button", { name: "Prepare revision request" }).click();
  await expect(page.getByLabel("Message Career Lab")).toHaveValue(/section "Experience"/);
  await expect(page.getByRole("button", { name: "Remove Selected draft" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Current profile" })).toBeVisible();
  await page.screenshot({ path: "e2e/__screenshots__/agui-draft-workspace.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("Career Lab keeps setup and reference context out of the starter", async ({ page }) => {
  await page.goto("/career-lab");
  await expect(page.getByRole("heading", { name: "Career Lab" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create Career Lab session" })).toBeVisible();
  await expect(page.getByText("Session setup")).toHaveCount(0);
  await expect(page.getByText("Reference context")).toHaveCount(0);
});

test("Career Lab does not overflow a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/career-lab");
  await expect(page.getByRole("heading", { name: "Career Lab" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("Career Lab reveals live reference filters only for an active session", async ({ page }) => {
  await page.unrouteAll();
  await mockCareerLab(page, true);
  await page.goto("/career-lab");
  await expect(page.getByText("Session setup")).toBeVisible();
  await expect(page.getByText("Reference context")).toBeVisible();
  await page.getByText("Job and resume context").click();
  await page.getByRole("combobox", { name: "Job source" }).selectOption("linkedin");

  const job = page.getByRole("combobox", { name: "Job", exact: true });
  await expect(job.getByRole("option", { name: /Acme · Staff Engineer/ })).toHaveCount(1);
  await expect(job.getByRole("option", { name: /Globex · Product Lead/ })).toHaveCount(0);
  await job.selectOption("7");
  await expect(job).toHaveValue("7");
  await page.getByLabel("Find a job").fill("Globex");
  await expect(job).toHaveValue("");
  await expect(job.getByRole("option", { name: /Acme · Staff Engineer/ })).toHaveCount(0);
  await expect(job.getByRole("option", { name: /Globex · Product Lead/ })).toHaveCount(1);
  await expect(page.getByRole("combobox", { name: "Job status" }).getByRole("option", { name: "applied" })).toHaveCount(1);
  await expect(page.getByRole("combobox", { name: "Job status" }).getByRole("option", { name: "tailored" })).toHaveCount(0);
});
