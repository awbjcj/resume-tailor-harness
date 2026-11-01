import { expect, test } from "@playwright/test";
import { mockEmptyRuns } from "./support";

for (const language of ["en", "zh-CN"] as const) {
  for (const width of [320, 1280]) {
    test(`profile change approval ${language} at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem("resume-tailor-harness-language", value), language);
      await mockEmptyRuns(page);
      await page.route("**/api/transcribe/availability", (route) => route.fulfill({ json: { available: false } }));
      await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/run-completions?*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/workspace-agent/proposals?*", (route) => route.fulfill({ json: { proposals: [], nextOffset: null } }));
      await page.route("**/api/setup/status", (route) => route.fulfill({ json: {
        complete: false, secrets: { anyLlmKey: true }, profile: { documentCount: 0, hasResume: false },
        search: { configured: false }, sources: { enabledCount: 0 },
      } }));
      let applied = false;
      let approvals = 0;
      let noteSaved = false;
      let noteTitle = "Migration ownership";
      let noteSummary = "Led the platform migration.";
      const revision = "a".repeat(64);
      const session = () => ({
        sessionId: "s1", startedAt: "2026-11-01T12:00:00Z", status: "active",
        turns: [{ role: "coach", kind: "profile_changes", text: "Review your requested change.", at: "2026-11-01T12:00:01Z" }],
        topics: [{ id: "t1", gap: "Profile", status: "open" }],
        draftNotes: [{ topicId: "t1", title: noteTitle, summary: noteSummary, quotes: ["I led the platform migration."], status: noteSaved ? "saved" : "pending" }],
        changeDrafts: [{ id: "d1", title: "Update your headline", revision, status: applied ? "applied" : "pending",
          quotes: ["Change my headline to Backend Engineer"],
          previews: [{ entity: "profile", operation: "update", label: "Update profile",
            before: { contact: { headline: "Engineer" } }, after: { contact: { headline: "Backend Engineer" } } }],
        }],
      });
      await page.route("**/api/profile/coach/sessions", (route) => route.fulfill({ json: { sessions: [{
        sessionId: "s1", status: "active", startedAt: "2026-11-01T12:00:00Z", topicCount: 1, savedNoteCount: 0,
      }] } }));
      await page.route("**/api/profile/coach/sessions/s1", (route) => route.fulfill({ json: session() }));
      await page.route("**/api/profile/coach/sessions/s1/changes/d1", async (route) => {
        expect(route.request().postDataJSON()).toEqual({ decision: "apply", revision });
        approvals += 1;
        applied = true;
        await route.fulfill({ json: session() });
      });
      await page.route("**/api/profile/coach/sessions/s1/notes/t1", async (route) => {
        const body = route.request().postDataJSON();
        expect(body).toEqual({ title: "Migration lead", summary: "Led the migration and handover.", quotes: ["I led the platform migration."] });
        noteTitle = body.title;
        noteSummary = body.summary;
        noteSaved = true;
        await route.fulfill({ json: session() });
      });
      await page.goto("/coach");
      await expect(page).toHaveURL(/\/coach$/);
      await expect(page.getByText("Update your headline", { exact: true })).toBeVisible();
      await expect(page.getByText("Backend Engineer", { exact: true })).toBeVisible();
      expect(approvals).toBe(0);
      await page.addStyleTag({ content: "html { font-size: 20px; }" });
      const apply = page.getByRole("button", { name: language === "en" ? "Apply changes" : "应用更改", exact: true });
      await apply.scrollIntoViewIfNeeded();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("profile-changes.png"), fullPage: true });
      await apply.click();
      await expect(page.getByText(language === "en" ? "Saved" : "已保存", { exact: true })).toBeVisible();
      expect(approvals).toBe(1);
      await expect(apply).toHaveCount(0);
      await page.getByRole("button", { name: language === "en" ? "Edit note" : "编辑笔记", exact: true }).click();
      await page.getByRole("textbox", { name: language === "en" ? "Title" : "标题", exact: true }).fill("Migration lead");
      await page.getByRole("textbox", { name: language === "en" ? "Summary" : "摘要", exact: true }).fill("Led the migration and handover.");
      expect(noteSaved).toBe(false);
      await page.getByRole("button", { name: language === "en" ? "Save note" : "保存笔记", exact: true }).click();
      await expect(page.getByText(language === "en" ? "Added to profile" : "已加入个人资料", { exact: true })).toBeVisible();
      await expect(page.getByRole("textbox", { name: language === "en" ? "Summary" : "摘要", exact: true })).toHaveCount(0);
    });
  }
}
