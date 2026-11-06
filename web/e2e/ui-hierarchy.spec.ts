import { expect, test } from "@playwright/test";
import { PROVIDER_SETUP } from "./support";

const pagination = { page: 1, pageSize: 200, totalItems: 0, totalPages: 1 };
const paged = { data: [], pagination };
const sessionList = { sessions: [], activeSessions: [], activeSessionId: null, pagination };
const review = {
  maxRounds: 3, scoreThreshold: 85, mergedAdvisory: true, evidencePortfolioEnabled: false,
  earlyStopOnRegression: false, tailorTier: "premium", reviserTier: "premium",
  provenanceRetryBudget: 1, styleGuidePath: "config/style_guide.md",
  reviewers: [{ name: "fact-check", gate: true, weight: 0, modelTier: "premium", scoreBands: false }],
  lengthBudget: {
    pageTarget: 2, maxExperiences: 5, maxProjects: 4, maxEvidenceOwners: 8,
    minBulletsPerRole: 5, maxBulletsPerRole: 7, minBulletsPerProject: 4,
    maxBulletsPerProject: 6, targetTotalBullets: 40, minAspectsPerOwner: 3,
    targetSkills: 40, maxSkillsPerCategory: 12,
  },
};

const responses: Record<string, unknown> = {
  "/api/health": { googleOauthConfigured: true, emailConfigured: true },
  "/api/setup/status": {
    secrets: { anthropicKey: true, anyLlmKey: true },
    profile: { documentCount: 1, hasResume: true, canRebuild: true, freshness: "current", factsBuiltAt: "2026-11-04T12:00:00Z", githubUsername: null },
    search: { configured: true }, sources: { enabledCount: 1 }, complete: true,
  },
  "/api/setup/provider": PROVIDER_SETUP,
  "/api/runs": paged,
  "/api/errors": { records: [] },
  "/api/notifications": [],
  "/api/run-completions": [],
  "/api/board-views": [],
  "/api/workspace-agent/proposals": { proposals: [], nextOffset: null },
  "/api/dashboard/summary": {
    statusCounts: { raw: 2, shortlisted: 3, approved: 1, tailored: 1, rendered: 1 },
    queues: { triage: 2, approve: 3, tailor: 1, apply: 1 }, applied: 4,
  },
  "/api/profile/coach/sessions": sessionList,
  "/api/interview/sessions": sessionList,
  "/api/scout/sessions": sessionList,
  "/api/career-lab/sessions": sessionList,
  "/api/career-lab/skills": { skills: [] },
  "/api/transcribe/availability": { available: false },
  "/api/profile/sources": [{ id: "resume", filename: "resume.pdf", mode: "literal", origin: "upload", primary: true, fileExists: true, incorporated: true }],
  "/api/profile/documents": [],
  "/api/profile/sources/github-exclusions": [],
  "/api/profile/skeleton": [],
  "/api/profile/skills": [],
  "/api/profile/skills/cleanup": { enabled: false, candidates: [] },
  "/api/profile/matrix": { groups: [], categories: [], rows: [] },
  "/api/profile/suppressed-skills": [],
  "/api/config/profile": { githubUsername: null, githubRepoAllow: [], githubRepoDeny: [], githubRepoLimit: 20 },
  "/api/config/search": { keywords: ["platform"], titles: ["Software Engineer"], locations: ["Remote"], remotePolicy: ["remote"] },
  "/api/config/application-profile": {},
  "/api/config/models": { cheapModel: "openai:test", midModel: "openai:test", premiumModel: "openai:test" },
  "/api/config/models/catalog": [],
  "/api/config/review": review,
  "/api/config/review-deep": review,
  "/api/config/render": { template: "classic", fitOnePage: true },
  "/api/config/render/templates": [],
  "/api/config/prune": { fitThreshold: 30, staleDays: 30, retentionDays: 90 },
  "/api/config/style-guide": { content: "Use concise, specific language." },
  "/api/agents/prompts": [],
  "/api/settings/sections": [],
  "/api/secrets": [{ key: "openaiApiKey", isSet: true, hint: "1234" }],
  "/api/sources": [],
  "/api/scrape/sources": [],
  "/api/application-accounts": { configured: true, accounts: [], autoRegister: false },
  "/api/gmail/status": { connected: false, scopes: [], draftCapable: false, clientSource: "platform" },
  "/api/mailboxes": { providers: [], accounts: [] },
  "/api/email-notifications": {
    email: "applicant@example.test", enabled: false, frequency: "weekly", pendingReviews: true,
    statistics: true, reminders: true, verifiedAt: null, verificationPending: false, deliveryAvailable: true,
  },
  "/api/applications": { technicalRoundColumns: 0, rows: [] },
  "/api/applications/comparison": { items: [] },
  "/api/analytics": { bySource: [], byBand: [] },
  "/api/analytics/timeline": { flows: [], cycleTimes: [], activePipeline: [], offers: [] },
  "/api/match-gap": { targetTotal: 0, jobs: [], skills: [], domains: [], categories: [], edges: [] },
  "/api/account/usage": { weightedTotal: 0, ownKeyWeightedTotal: 0, budget: 0 },
  "/api/account/tokens": { tokens: [] },
  "/api/admin/users": { users: [] },
  "/api/admin/system/defaults": { weeklyTokenBudget: 1000000, maxActiveJobs: 2000, maxConcurrentRuns: 2 },
  "/api/admin/quota-summary": { monthlySpendMicros: 0, monthlyCapMicros: 500000000, remainingMicros: 500000000, unpricedCallCount: 0, nextResetAt: "2026-12-01T00:00:00Z" },
  "/api/admin/quota-tiers": paged,
  "/api/admin/quota-accounts": paged,
  "/api/admin/llm-rates": paged,
  "/api/admin/quota-operations": paged,
  "/api/admin/routing": { baseUrl: "", providers: [] },
  "/api/admin/routing/decisions": { mode: "standard", apiKeySet: false, apiKeyHint: null },
};

const routes = [
  "/", "/profile", "/profile?tab=skills", "/coach", "/interview", "/career-lab", "/scout",
  "/triage", "/shortlist", "/pipeline", "/match-gap", "/applications", "/analytics", "/account",
  "/admin", "/admin/quotas", "/admin/routing", "/settings/search", "/settings/sources",
  "/settings/pruning", "/settings/review", "/settings/style-guide", "/settings/rendering",
  "/settings/application-profile", "/settings/password-manager", "/settings/notifications",
  "/settings/keys", "/settings/agent-prompts", "/settings/backup",
  "/setup/keys", "/setup/documents", "/setup/search", "/setup/sources", "/setup/finish",
  "/login", "/register", "/forgot-password", "/complete-profile",
  "/verify-email?email=applicant@example.test", "/reset-password?email=applicant@example.test",
];

for (const { language, width, theme } of [
  { language: "en", width: 1440, theme: "light" },
  { language: "zh-CN", width: 375, theme: "dark" },
]) {
  test.describe(`${language} at ${width}px`, () => {
    for (const destination of routes) {
      test(`one title and main landmark on ${destination}`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ reducedMotion: "reduce" });
        await page.addInitScript(({ language, theme }) => {
          localStorage.setItem("resume-tailor-harness-language", language);
          localStorage.setItem("theme", theme);
        }, { language, theme });
        const errors: string[] = [];
        const unexpected: string[] = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.route("**/api/**", async (route) => {
          const url = new URL(route.request().url());
          const pathname = url.pathname;
          if (!pathname.startsWith("/api/")) return route.continue();
          if (pathname === "/api/config/language") return route.fulfill({ json: route.request().postDataJSON() });
          if (pathname === "/api/auth/me") {
            const authPage = /^\/(login|register|forgot-password|complete-profile|verify-email|reset-password)/.test(destination);
            return route.fulfill({ json: authPage
              ? { username: null, role: null, authRequired: true }
              : { username: "owner", role: "admin", authRequired: false } });
          }
          if (["/api/triage", "/api/shortlist", "/api/pipeline"].includes(pathname)) {
            return route.fulfill({ json: { ...paged, facets: {}, total: 0 } });
          }
          if (Object.hasOwn(responses, pathname)) return route.fulfill({ json: responses[pathname] });
          unexpected.push(pathname);
          return route.fulfill({ status: 404, json: { error: { message: "Missing UI fixture" } } });
        });
        await page.goto(destination);
        await expect(page.locator("h1")).toHaveCount(1);
        await expect(page.locator("h1")).toBeVisible();
        await expect(page.getByRole("main")).toHaveCount(1);
        await expect(page.locator("header.app-chrome h1")).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
        if (["/", "/profile", "/coach", "/settings/search", "/shortlist", "/login"].includes(destination)) {
          await page.screenshot({ path: testInfo.outputPath("page.png"), fullPage: true });
        }
        expect(errors).toEqual([]);
        expect(unexpected).toEqual([]);
      });
    }
  });
}
