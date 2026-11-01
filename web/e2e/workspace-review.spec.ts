import { expect, test } from "@playwright/test";
import type { components } from "../src/lib/api/schema";
import { mockEmptyRuns } from "./support";

for (const language of ["en", "zh-CN"] as const) {
  for (const theme of ["light", "dark"] as const) {
  for (const width of [320, 375, 768, 812, 1920]) {
    test(`workspace review ${language} ${theme} at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 812 ? 375 : 900 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.addInitScript(({ language, theme }) => {
        localStorage.setItem("resume-tailor-harness-language", language);
        localStorage.setItem("theme", theme);
      }, { language, theme });
      await mockEmptyRuns(page);
      await page.route("**/api/transcribe/availability", (route) => route.fulfill({ json: { available: false } }));
      await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/run-completions?*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/setup/status", (route) => route.fulfill({ json: {
        complete: false, secrets: { anyLlmKey: true }, profile: { documentCount: 0, hasResume: false },
        search: { configured: false }, sources: { enabledCount: 0 },
      } }));
      const session = {
        sessionId: "s1", startedAt: "2026-11-01T12:00:00Z", status: "active",
        turns: [{ role: "coach", text: "Review the proposed workspace changes.", at: "2026-11-01T12:00:01Z" }],
        topics: [{ id: "t1", gap: "Profile", status: "open" }], draftNotes: [], changeDrafts: [],
      };
      await page.route("**/api/profile/coach/sessions", (route) => route.fulfill({ json: { sessions: [{
        sessionId: "s1", status: "active", startedAt: session.startedAt, topicCount: 1, savedNoteCount: 0,
      }] } }));
      await page.route("**/api/profile/coach/sessions/s1", (route) => route.fulfill({ json: session }));
      const proposal: components["schemas"]["ProposalOut"] = {
        id: "p1", title: "Prepare for the recruiter conversation", digest: "a".repeat(64), surface: "coach", sessionId: "s1",
        createdAt: session.startedAt, expiresAt: "2099-01-01T00:00:00Z",
        actions: [{
          id: "a1", change: { operation: "note.update", job_id: 7, target_id: 1, values: {},
            reason: "Keep the ownership example ready for your next conversation.", citations: [`https://example.com/${"evidence-".repeat(15)}`] },
          before: { title: "Platform support", body: "Helped with the migration." }, after: { title: "Platform ownership", body: "Led the migration and documented the handover.", reference: "reference".repeat(18) }, receipt: null,
        }, {
          id: "a2", change: { operation: "job.delete", job_id: 8, target_id: null, values: {},
            reason: "Remove the duplicate role after checking the original entry.", citations: [] },
          before: { title: "Duplicate platform role" }, after: null, receipt: null,
        }],
      };
      const requests: unknown[] = [];
      await page.route("**/api/workspace-agent/proposals?*", (route) => route.fulfill({ json: { proposals: [proposal], nextOffset: null } }));
      await page.route("**/api/workspace-agent/proposals/p1/review", async (route) => {
        const body = route.request().postDataJSON();
        requests.push(body);
        for (const action of proposal.actions.filter((item) => body.actionIds.includes(item.id))) {
          action.receipt = { state: "applied", result: { noteId: 1 }, approvedBy: "local-user", createdAt: session.startedAt };
        }
        await route.fulfill({ json: proposal });
      });

      await page.goto("/coach");
      const review = page.getByRole("region", { name: language === "en" ? "Workspace changes" : "工作区更改", exact: true });
      await expect(review.getByRole("heading", { name: proposal.title })).toBeVisible();
      await page.addStyleTag({ content: "html { font-size: 20px; }" });
      const checkbox = review.getByRole("checkbox").nth(1);
      await expect(checkbox).not.toBeChecked();
      await checkbox.focus();
      await page.keyboard.press("Space");
      await expect(checkbox).toBeChecked();
      await page.keyboard.press("Space");
      await expect(checkbox).not.toBeChecked();
      expect(requests).toEqual([]);
      // The preview must remain readable even in a narrow panel on a wide screen.
      const before = review.getByText(language === "en" ? "Before" : "更改前", { exact: true }).first();
      if (width === 1920) {
        await review.evaluate((element) => { element.style.maxWidth = "400px"; });
      }
      const columns = await before.locator("../..").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
      expect(columns).toBe(1);
      if (width === 1920) {
        await review.evaluate((element) => { element.style.maxWidth = ""; });
        await expect.poll(() => before.locator("../..").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length)).toBe(2);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
      expect(await review.evaluate((element) => Array.from(element.querySelectorAll<HTMLElement>("[data-slot=card], dl, dd, button"))
        .filter((item) => item.scrollWidth > item.clientWidth + 1).map((item) => item.tagName))).toEqual([]);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: testInfo.outputPath("review.png"), fullPage: true });

      const approve = review.getByRole("button", { name: language === "en" ? "Approve and save" : "批准并保存", exact: true });
      await approve.click();
      await expect(review.getByText(language === "en" ? "Saved" : "已保存", { exact: true })).toBeVisible();
      expect(requests).toEqual([{ digest: proposal.digest, actionIds: ["a1"], decision: "apply" }]);
      await expect(review.getByRole("checkbox")).not.toBeChecked();
      await review.getByRole("checkbox").check();
      await approve.click();
      let dialog = page.getByRole("alertdialog");
      const cancelName = language === "en" ? "Back to review" : "返回审核";
      await expect(dialog.getByRole("button", { name: cancelName })).toBeFocused();
      await expect(dialog.getByText("Duplicate platform role", { exact: true })).toBeVisible();
      expect(requests).toHaveLength(1);
      await page.keyboard.press("Escape");
      await expect(dialog).not.toBeVisible();
      await expect(approve).toBeFocused();
      await approve.click();
      dialog = page.getByRole("alertdialog");
      await expect(dialog).toBeVisible();
      await expect(dialog).toHaveCSS("opacity", "1");
      await expect(page.locator("[data-slot=alert-dialog-overlay]")).toHaveCSS("opacity", "1");
      expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("confirmation.png"), animations: "disabled" });
      await dialog.getByRole("button", { name: language === "en" ? "Save and remove" : "保存并移除", exact: true }).click();
      await expect(dialog).not.toBeVisible();
      expect(requests).toEqual([
        { digest: proposal.digest, actionIds: ["a1"], decision: "apply" },
        { digest: proposal.digest, actionIds: ["a2"], decision: "apply" },
      ]);
      await expect(review.getByRole("checkbox")).toHaveCount(0);
    });
  }
  }
}
