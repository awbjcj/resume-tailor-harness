import { expect, test } from "@playwright/test";

test("keeps selected actions, interview banner, and notifications usable while switching languages on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "zh-CN"));
  const job = {
    jobId: 7, company: "Acme", title: "Platform Engineer", status: "tailored",
    fitScore: 80, jdPreview: "Build reliable services.", critiqueJson: null,
    pdfPath: null, applicationStatus: null, hasProgress: true,
  };
  const emptyPage = { data: [], pagination: { page: 1, pageSize: 20, totalItems: 0, totalPages: 1 } };
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { username: "owner", role: "admin", authRequired: false } });
    if (url.pathname === "/api/setup/status") return route.fulfill({ json: {
      secrets: { anthropicKey: true, anyLlmKey: true },
      profile: { documentCount: 1, hasResume: true, canRebuild: true, freshness: "current", factsBuiltAt: null, githubUsername: null },
      search: { configured: true }, sources: { enabledCount: 1 }, complete: true,
    } });
    if (url.pathname === "/api/config/language") return route.fulfill({ json: route.request().postDataJSON() });
    if (url.pathname === "/api/interview/sessions") return route.fulfill({ json: { sessions: [{
      sessionId: "active", jobId: 7, company: "Acme", title: "Platform Engineer", status: "active",
      startedAt: "2026-10-23T12:00:00Z", endedAt: null, archivedAt: null, askedCount: 1, questionCount: 4,
    }] } });
    if (url.pathname === "/api/notifications") return route.fulfill({ json: [{
      id: 1, applicationId: 1, kind: "follow_up", proposedStatus: "", evidence: "No activity for 20 days: Acme · Platform Engineer",
      messageId: "followup", state: "pending", createdAt: "2026-10-23T12:00:00Z", jobId: 7, company: "Acme", title: "Platform Engineer",
    }] });
    if (url.pathname === "/api/run-completions" || url.pathname === "/api/board-views") return route.fulfill({ json: [] });
    if (url.pathname === "/api/jobs/bulk") return route.fulfill({ json: { affected: 1, skipped: 0, reasons: {} } });
    if (url.pathname === "/api/pipeline") {
      const rows = url.searchParams.get("status") === "tailored" ? [job] : [];
      return route.fulfill({ json: {
        data: rows, pagination: { page: 1, pageSize: 1, totalItems: 5, totalPages: 5 },
        facets: { status: { tailored: 5 } }, total: 5,
      } });
    }
    return route.fulfill({ json: emptyPage });
  });

  await page.goto("/pipeline");
  await expect(page.getByRole("heading", { name: "求职流程" })).toBeVisible();
  await expect(page.getByRole("link", { name: "继续面试" })).toBeVisible();
  await page.getByRole("checkbox", { name: /Acme Platform Engineer/ }).check();
  await expect(page.getByRole("status", { name: "已选择 1 项" })).toBeVisible();
  await expect(page.getByText("已选中全部 1 条已加载的结果。")).toBeVisible();
  await expect(page.getByRole("button", { name: "选中符合此筛选条件的全部 5 条结果" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.getByRole("button", { name: "归档", exact: true }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByText("归档所选的 1 个职位？")).toBeVisible();
  await expect(dialog.getByText("将影响 1 个职位。")).toBeVisible();
  await dialog.getByRole("button", { name: "取消" }).click();
  await expect(dialog).toBeHidden();

  await page.getByRole("button", { name: "通知（1 条待处理）" }).click();
  await expect(page.getByText("20 天没有新动态：Acme · Platform Engineer")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("combobox", { name: "语言", exact: true }).selectOption("en");
  await expect(page.getByRole("status", { name: "1 selected" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Select all 5 matching this filter" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Resume", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(dialog.getByText("Archive 1 selected job?")).toBeVisible();
  await expect(dialog.getByText("1 job affected.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
