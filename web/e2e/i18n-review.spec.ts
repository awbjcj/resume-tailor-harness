import { expect, test } from "@playwright/test";

import { mockEmptyRuns } from "./support";

test.use({ locale: "zh-CN" });

const reviewConfig = {
  maxRounds: 3,
  scoreThreshold: 85,
  mergedAdvisory: false,
  evidencePortfolioEnabled: false,
  earlyStopOnRegression: false,
  tailorTier: "premium",
  reviserTier: "premium",
  provenanceRetryBudget: 1,
  styleGuidePath: "config/style_guide.md",
  reviewers: [
    { name: "fact-check", gate: true, weight: 0, modelTier: "premium", scoreBands: false },
    { name: "ats-keyword", gate: false, weight: 1, modelTier: "mid", scoreBands: true },
  ],
  lengthBudget: {
    pageTarget: 2,
    maxExperiences: 5,
    maxProjects: 4,
    maxEvidenceOwners: 8,
    minBulletsPerRole: 5,
    maxBulletsPerRole: 7,
    minBulletsPerProject: 4,
    maxBulletsPerProject: 6,
    targetTotalBullets: 40,
    minAspectsPerOwner: 3,
    targetSkills: 40,
    maxSkillsPerCategory: 12,
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route(/\/api\/run-completions(?:\?.*)?$/, (route) => route.fulfill({ json: [] }));
  await page.route("**/api/setup/status", (route) =>
    route.fulfill({
      json: {
        secrets: { anthropicKey: true, anyLlmKey: true },
        profile: { documentCount: 1, hasResume: true, factsBuiltAt: null, githubUsername: null },
        search: { configured: true },
        sources: { enabledCount: 1 },
        complete: true,
      },
    }),
  );
  await mockEmptyRuns(page);
  await page.route("**/api/config/review", async (route) => {
    const body = route.request().method() === "PUT" ? route.request().postDataJSON() : reviewConfig;
    await route.fulfill({ json: body });
  });
  await page.route("**/api/config/review-deep", async (route) => {
    const body = route.request().method() === "PUT" ? route.request().postDataJSON() : reviewConfig;
    await route.fulfill({ json: body });
  });
});

test("renders localized gates, tiers, and reviewer notes without altering model values", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/settings/review");

  await expect(page.getByText("硬性门槛", { exact: true })).toBeVisible();
  await expect(page.getByText(/硬性门槛评审未通过时，无论本轮得分如何，本轮都不通过/)).toBeVisible();
  await expect(page.getByText(/真实性要求/)).toBeVisible();
  await expect(page.getByRole("button", { name: "写作模型档位：标准型" })).toBeVisible();
  await expect(page.getByRole("button", { name: "修订模型档位：高级型" })).toBeVisible();
  await expect(page.getByText("mid", { exact: true })).toHaveCount(0);
  await expect(page.getByText("premium", { exact: true })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("switches settings navigation language while preserving unsaved form input", async ({ page }) => {
  await page.goto("/settings/review");
  await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
  await expect(page.getByRole("heading", { name: "Review panel", exact: true })).toBeVisible();
  await expect(page.getByText("If a gated reviewer fails, the round fails regardless of its score. Gate reviewers do not contribute a score, so their weight and score bands are disabled.")).toBeVisible();
  await page.locator("#maxRounds").fill("4");
  await page.getByRole("combobox", { name: "Language", exact: true }).selectOption("zh-CN");
  await expect(page.getByRole("link", { name: "备份", exact: true }).last()).toBeVisible();
  await expect(page.getByRole("link", { name: "助手提示词", exact: true }).last()).toBeVisible();
  await expect(page.locator("#maxRounds")).toHaveValue("4");
  await expect(page.getByRole("button", { name: "保存更改", exact: true })).toBeVisible();
});

test("localizes built-in template labels without changing custom template names or selection", async ({ page }) => {
  await page.route("**/api/config/render", (route) => route.fulfill({ json: { template: "classic", fitOnePage: true } }));
  await page.route("**/api/config/render/templates", (route) => route.fulfill({ json: [
    { id: "classic", title: "Classic", description: "Traditional serif layout for general applications and conservative industries.", kind: "bundled" },
    { id: "custom:Classic", title: "Classic", description: "Uploaded template", kind: "custom" },
  ] }));
  await page.goto("/settings/rendering");

  await expect(page.getByText("经典", { exact: true })).toBeVisible();
  await expect(page.getByText("Classic", { exact: true })).toBeVisible();
  await expect(page.getByText("传统衬线字体布局，适合一般求职和风格较保守的行业。")).toBeVisible();
  await page.getByRole("radio", { name: "使用Classic模板" }).click();
  await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
  await expect(page.getByRole("radio", { name: "Use Classic template" })).toHaveCount(2);
  await expect(page.getByRole("radio", { name: "Use Classic template" }).last()).toBeChecked();
});

test("localizes built-in agent labels while preserving the original instructions", async ({ page }) => {
  await page.route("**/api/agents/prompts", (route) => route.fulfill({ json: [
    {
      key: "tailor-writer", title: "Resume writer", stage: "tailoring",
      description: "Writes a targeted resume under the profile fact-lock.",
      instructions: ["Keep the original instruction."], guidance: null, editable: true,
    },
    {
      key: "email-writer", title: "Email writer", stage: "email",
      description: "Drafts fact-grounded job-search emails.",
      instructions: [..."Draft an email.", "Additional quality rules."], guidance: null, editable: true,
    },
  ] }));
  await page.goto("/settings/agent-prompts");

  await expect(page.getByText("依据个人资料中的事实撰写针对职位的简历。")).toBeVisible();
  await page.getByText("简历写作助手", { exact: true }).click();
  await expect(page.getByText("内置指令以原文显示。")).toBeVisible();
  await expect(page.getByText("Keep the original instruction.")).toBeVisible();
  await page.getByText("邮件写作助手", { exact: true }).click();
  await expect(page.getByText("Draft an email.", { exact: true })).toBeVisible();
});

test("localizes interview style values and keeps the answer when switching languages", async ({ page }, testInfo) => {
  const summary = {
    sessionId: "translation-session", jobId: 7, resumeVersionId: 3,
    company: "Acme", title: "Engineer", status: "active",
    startedAt: "2026-10-23T12:00:00Z", endedAt: null, archivedAt: null,
    askedCount: 1, questionCount: 4,
  };
  await page.route("**/api/interview/sessions*", (route) => route.fulfill({ json: { sessions: [summary] } }));
  await page.route("**/api/interview/sessions/translation-session", (route) => route.fulfill({ json: {
    ...summary, concluded: false,
    style: { stage: "technical", demeanor: "neutral", difficulty: "standard", questionCount: 4, extra: "", responseMode: "text" },
    progress: { asked: 1, total: 4 }, plan: null, debrief: null,
    turns: [{ role: "interviewer", text: "请介绍一个你主导的项目。", questionId: "q1", isFollowup: false, at: summary.startedAt }],
  } }));
  await page.goto("/interview?session=translation-session");
  await expect(page.getByText("技术面试", { exact: true })).toBeVisible();
  await expect(page.getByText("平和", { exact: true })).toBeVisible();
  await expect(page.getByText("标准", { exact: true })).toBeVisible();
  await expect(page.getByText("第 1 题，共 4 题", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "结束面试", exact: true }).click();
  await expect(page.getByText("面试官将停止提问，系统会对你目前的回答评分。")).toBeVisible();
  await page.getByRole("button", { name: "继续", exact: true }).click();
  const answer = page.locator("textarea").last();
  await answer.fill("保留这段尚未提交的回答");
  await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
  await expect(page.getByText("technical", { exact: true })).toBeVisible();
  await expect(page.getByText("Question 1 of 4", { exact: true })).toBeVisible();
  await expect(page.getByText(/^Question 1 of 4 ·/)).toBeVisible();
  await expect(answer).toHaveValue("保留这段尚未提交的回答");
  await page.locator('[data-slot="alert-dialog-trigger"]').filter({ hasText: "End interview" }).click();
  await expect(page.getByText("The interviewer will stop, and your coach will score the answers you have given so far.")).toBeVisible();
  await page.getByRole("button", { name: "Keep going", exact: true }).click();
  await page.getByRole("combobox", { name: "Language", exact: true }).selectOption("zh-CN");
  await expect(page.getByText("技术面试", { exact: true })).toBeVisible();
  await expect(page.getByText("第 1 题，共 4 题", { exact: true })).toBeVisible();
  await expect(page.getByText(/^第 1 题，共 4 题 ·/)).toBeVisible();
  await expect(answer).toHaveValue("保留这段尚未提交的回答");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByText("技术面试", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("chinese-interview.png"), fullPage: true });
});
