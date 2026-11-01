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
      await page.route("**/api/setup/status", (route) => route.fulfill({ json: {
        complete: false, secrets: { anyLlmKey: true }, profile: { documentCount: 0, hasResume: false },
        search: { configured: false }, sources: { enabledCount: 0 },
      } }));
      let applied = false;
      let approvals = 0;
      const revision = "a".repeat(64);
      const session = () => ({
        sessionId: "s1", startedAt: "2026-11-01T12:00:00Z", status: "active",
        turns: [{ role: "coach", kind: "profile_changes", text: "Review your requested change.", at: "2026-11-01T12:00:01Z" }],
        topics: [{ id: "t1", gap: "Profile", status: "open" }], draftNotes: [],
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
      await expect(page.getByText(language === "en" ? "Applied" : "已应用", { exact: true })).toBeVisible();
      expect(approvals).toBe(1);
      await expect(apply).toHaveCount(0);
    });
  }
}
