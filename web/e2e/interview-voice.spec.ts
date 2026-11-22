import { expect, test } from "@playwright/test";
import { writeFileSync } from "node:fs";

import { mockEmptyRuns } from "./support";

test.use({
  channel: "chrome",
  permissions: ["microphone"],
  launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"] },
});

function silenceWav() {
  const bytes = Buffer.alloc(44 + 16_000 * 2);
  bytes.write("RIFF", 0); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(16_000, 24); bytes.writeUInt32LE(32_000, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36); bytes.writeUInt32LE(bytes.length - 44, 40);
  return bytes;
}

test("records in Chromium, reviews a transcript, and plays interviewer audio", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockEmptyRuns(page);
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: {
    secrets: { anthropicKey: true, anyLlmKey: true },
    profile: { documentCount: 1, hasResume: true, factsBuiltAt: "2026-06-01T00:00:00Z", githubUsername: null },
    search: { configured: true }, sources: { enabledCount: 1 }, complete: true,
  } }));
  const session = {
    sessionId: "s1", jobId: 7, resumeVersionId: 3, company: "Acme", title: "Engineer",
    startedAt: "2026-07-18T12:00:00Z", endedAt: null, status: "active", concluded: false,
    askedCount: 1, questionCount: 4, overallScore: null, archivedAt: null,
    style: { stage: "technical", demeanor: "neutral", difficulty: "standard", questionCount: 4, extra: "", responseMode: "audio_preferred" },
    progress: { asked: 1, total: 4 }, plan: null, debrief: null,
    turns: [{ role: "interviewer", text: "Tell me about a project.", questionId: "q1", isFollowup: false, at: "2026-07-18T12:01:00Z", audioStatus: "ready", audioUrl: "/api/interview/sessions/s1/turns/0/audio" }],
  };
  await page.route("**/api/interview/sessions*", (route) => route.fulfill({ json: { sessions: [session] } }));
  await page.route("**/api/interview/sessions/s1", (route) => route.fulfill({ json: session }));
  await page.route("**/api/interview/sessions/s1/turns/0/audio", (route) => route.fulfill({ status: 200, contentType: "audio/wav", body: silenceWav() }));
  await page.route("**/api/transcribe/official/availability", (route) => route.fulfill({ json: {
    enabled: true, available: true, warning: false, optionalWorkPaused: false,
    spentMicros: 10, heldMicros: 0, remainingMicros: 14_999_990,
  } }));
  let uploadBytes = 0;
  await page.route("**/api/transcribe/official", (route) => {
    const request = route.request();
    const body = request.postDataBuffer();
    const boundary = request.headers()["content-type"]?.match(/boundary=(.+)$/)?.[1];
    if (body && boundary) {
      const fileHeader = body.indexOf(Buffer.from('name="file"'));
      const start = body.indexOf(Buffer.from("\r\n\r\n"), fileHeader) + 4;
      const end = body.indexOf(Buffer.from(`\r\n--${boundary}`), start);
      if (fileHeader >= 0 && start >= 4 && end > start) {
        const clip = body.subarray(start, end);
        uploadBytes = clip.length;
        writeFileSync(test.info().outputPath("captured.webm"), clip);
      }
    }
    return route.fulfill({ json: { text: "A recorded answer", billingPending: false } });
  });
  let answers = 0;
  await page.route("**/api/interview/sessions/s1/messages", (route) => {
    answers += 1;
    return route.fulfill({ status: 202, json: { runId: "run-1" } });
  });

  await page.goto("/interview?session=s1");
  await expect(page.getByRole("button", { name: /record answer/i })).toBeVisible();
  await page.getByRole("button", { name: /record answer/i }).click();
  await expect(page.getByRole("button", { name: /stop and transcribe/i })).toBeVisible();
  await page.waitForTimeout(700); // A real MediaRecorder needs time to emit a non-empty clip.
  await page.getByRole("button", { name: /stop and transcribe/i }).click();
  await expect(page.getByRole("textbox", { name: "Your answer" })).toHaveValue("A recorded answer");
  expect(uploadBytes).toBeGreaterThan(500);
  expect(answers).toBe(0);
  await page.getByRole("textbox", { name: "Your answer" }).fill("Edited recorded answer");
  await expect(page.locator("audio")).toHaveCount(1);
  await expect.poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLAudioElement).readyState)).toBeGreaterThanOrEqual(2);
  await page.getByRole("button", { name: /replay audio|play audio/i }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLAudioElement).currentTime)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: "test-results/interview-voice-mobile.png", fullPage: true });
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await page.setViewportSize({ width: 812, height: 375 });
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.getByRole("button", { name: /record answer/i })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: "test-results/interview-voice-landscape-dark.png", fullPage: true });
  await page.getByRole("button", { name: /send message/i }).click();
  await expect.poll(() => answers).toBe(1);
});
