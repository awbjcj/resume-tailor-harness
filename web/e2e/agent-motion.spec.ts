import { expect, test, type Page } from "@playwright/test";

import { mockEmptyRuns } from "./support";

interface MotionSource {
  url: string;
  closed: boolean;
  onmessage: ((event: { data: string }) => void) | null;
}

declare global {
  interface Window { __motionSources: MotionSource[] }
}

async function mockAgent(page: Page, language = "en", theme = "light") {
  await mockEmptyRuns(page);
  await page.addInitScript(({ language, theme }) => {
    localStorage.setItem("resume-tailor-harness-language", language);
    localStorage.setItem("theme", theme);
    window.__motionSources = [];
    // Keep the real UI and reducer; let the test deliver individual SSE frames.
    class ControlledEventSource {
      closed = false;
      onmessage: ((event: { data: string }) => void) | null = null;
      onerror = null;
      constructor(public url: string) { window.__motionSources.push(this); }
      close() { this.closed = true; }
    }
    Object.defineProperty(window, "EventSource", { value: ControlledEventSource });
  }, { language, theme });
  const session = {
    sessionId: "motion-session", goal: "Review platform opportunities", status: "active",
    startedAt: "2026-10-19T12:00:00Z", endedAt: null, archivedAt: null,
    turns: [], proposals: [], recap: null, scrapeAvailable: true, scrapeUnavailableReason: null,
  };
  const run = {
    runId: "motion-run", kind: "scout-turn", state: "running", percent: 25,
    current: 1, total: 4, label: "Checking sources", error: null, result: null,
    meta: { sessionId: session.sessionId, turnCount: 0 },
  };
  await page.route("**/api/scout/sessions**", (route) => route.fulfill({ json: { sessions: [{ ...session, turnCount: 0 }] } }));
  await page.route("**/api/scout/sessions/motion-session", (route) => route.fulfill({ json: session }));
  await page.route("**/api/runs?*", (route) => route.fulfill({ json: { data: [run], pagination: { page: 1, pageSize: 200, totalItems: 1, totalPages: 1 } } }));
  await page.route("**/api/runs/motion-run", (route) => route.fulfill({ json: run }));
  await page.route("**/api/auth/link-token", (route) => route.fulfill({ json: { token: "motion-fixture", expiresInSeconds: 60 } }));
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/transcribe/availability", (route) => route.fulfill({ json: { available: false } }));
  await page.goto("/scout");
  await expect.poll(() => page.evaluate(() => window.__motionSources.some((source) => source.url.includes("/stream?") && !source.closed))).toBe(true);
}

async function emit(page: Page, index: number, tag: string, value: Record<string, unknown>) {
  await page.evaluate((event) => {
    for (const source of window.__motionSources) {
      if (!source.closed && source.url.includes("/stream?")) source.onmessage?.({ data: JSON.stringify(event) });
    }
  }, { i: index, t: tag, v: value });
}

const markdown = [
  "## Research plan", "", "1. Review **evidence**", "2. Compare `platform` roles", "",
  "| Company | Role | Location | Evidence | Next step |", "| --- | --- | --- | --- | --- |",
  "| Example | Engineer | Remote | Official careers page | Review the requirements |", "",
  "```ts", `const evidence = "${"verified-source/".repeat(20)}";`, "```", "",
  ...Array.from({ length: 12 }, (_, index) => `Paragraph ${index + 1}. Keep the research readable while the agent checks the next source.\n`),
].join("\n");

for (const scenario of [
  { language: "en", theme: "light", reducedMotion: "no-preference" as const, width: 1440 },
  { language: "zh-CN", theme: "dark", reducedMotion: "reduce" as const, width: 390 },
]) {
  test(`agent rendering and activity respect ${scenario.language}, ${scenario.theme}, ${scenario.reducedMotion}`, async ({ page }) => {
    await page.setViewportSize({ width: scenario.width, height: 1000 });
    await page.emulateMedia({ reducedMotion: scenario.reducedMotion });
    await mockAgent(page, scenario.language, scenario.theme);
    await emit(page, 0, "text", { text: markdown });
    const text = page.getByTestId("chat-part-text");
    await expect(text.getByRole("heading", { name: "Research plan" })).toBeVisible();
    expect(await text.evaluate((node) => node.closest('[role="status"], [aria-live]') !== null)).toBe(false);
    await expect(page.getByTestId("chat-streaming-response")).toHaveAttribute("aria-busy", "true");
    await expect(page.getByTestId("chat-stream-caret")).toHaveCSS("animation-name", scenario.reducedMotion === "reduce" ? "none" : "pulse");
    expect(await text.locator("ol").evaluate((node) => getComputedStyle(node).listStyleType)).toBe("decimal");
    const table = page.getByRole("region", { name: scenario.language === "en" ? "Table" : "表格", exact: true });
    await expect(table).toHaveCSS("overflow-x", "auto");
    const code = page.getByLabel(scenario.language === "en" ? "Code block" : "代码块", { exact: true });
    await expect(code).toHaveCSS("overflow-x", "auto");
    expect(await code.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);

    await emit(page, 1, "reasoning", { text: "Compare the official source with the saved profile." });
    await emit(page, 2, "tool_started", { callId: "source-1", name: "check_source", argsPreview: "Official careers page" });
    const tool = page.getByTestId("chat-part-tool");
    await expect(tool.locator("svg.lucide-loader-circle")).toHaveCSS("animation-name", scenario.reducedMotion === "reduce" ? "none" : "spin");
    await emit(page, 3, "tool_completed", { callId: "source-1", name: "check_source", resultPreview: Array.from({ length: 18 }, (_, i) => `Evidence ${i + 1}: official source confirmed.`).join("\n"), ok: true });
    await expect(tool.locator("svg.lucide-loader-circle")).toHaveCount(0);
    const trigger = tool.getByRole("button");
    await trigger.click();
    const disclosure = tool.locator('[data-slot="collapsible-content"]');
    await expect(disclosure).toBeVisible();
    await expect(disclosure).toHaveCSS("transition-property", scenario.reducedMotion === "reduce" ? "opacity" : "opacity, transform");
    const viewport = page.getByTestId("chat-viewport");
    await expect.poll(() => viewport.evaluate((node) => node.scrollHeight - node.clientHeight - node.scrollTop)).toBeLessThan(2);
    // Reverse the disclosure before its transition settles; Base UI must
    // ultimately hide it and restore the trigger's accessible state.
    await trigger.evaluate(async (node) => {
      node.click();
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      node.click();
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      node.click();
    });
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(disclosure).toBeHidden();

    await viewport.evaluate((node) => { node.scrollTop = 0; });
    await expect(page.getByRole("button", { name: scenario.language === "en" ? "Jump to latest" : "跳转到最新" })).toBeVisible();
    await expect.poll(() => viewport.evaluate((node) => node.scrollTop)).toBe(0);
    await emit(page, 4, "text", { text: "\n\nFinal summary.\n".repeat(12) });
    // Wait through layout and the observer's follow-up frame before judging
    // anchoring; an immediate assertion can miss a queued automatic scroll.
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    expect(await viewport.evaluate((node) => node.scrollTop)).toBe(0);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `output/agent-motion-${scenario.language}-${scenario.reducedMotion}.png`, fullPage: false });
    await emit(page, 5, "settled", {});
    await expect(page.getByTestId("chat-stream-caret")).toHaveCount(0);
    await expect(page.getByTestId("chat-streaming-response")).toHaveAttribute("aria-busy", "false");
    await emit(page, 6, "completed", {});
    expect(await page.evaluate(() => window.__motionSources.filter((source) => source.url.includes("/stream?")).every((source) => source.closed))).toBe(true);
  });
}

test("mobile sheet reverses from its edge and reduces to a stationary fade", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await mockAgent(page);
  const toggle = page.locator('[data-slot="sidebar-trigger"]');
  expect(await toggle.evaluate((node) => getComputedStyle(node).transitionProperty.split(", "))).toContain("scale");
  const bounds = await toggle.boundingBox();
  if (!bounds) throw new Error("Sidebar trigger must be visible");
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down();
  await expect(toggle).toHaveCSS("scale", "0.98");
  await page.mouse.up();
  const sheet = page.locator(".sheet-panel");
  await expect(sheet).toBeVisible();
  await expect(sheet).toHaveCSS("transition-property", "opacity, transform");
  await expect(sheet).toHaveCSS("transition-duration", "0.2s, 0.24s");
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down();
  await expect(toggle).toHaveCSS("scale", "none");
  await page.mouse.up();
  await expect(sheet).toBeVisible();
  await expect(sheet).toHaveCSS("transform", "none");
  await expect(sheet).toHaveCSS("transition-property", "opacity");
  // Check the more specific start/end selectors too, beyond the settled style.
  const phases = await sheet.evaluate((node) => {
    return ["data-starting-style", "data-ending-style"].map((attribute) => {
      node.setAttribute(attribute, "");
      const transform = getComputedStyle(node).transform;
      node.removeAttribute(attribute);
      return transform;
    });
  });
  expect(phases).toEqual(["none", "none"]);
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
});

test("cancellation settles a pending tool and removes continuous response feedback", async ({ page }) => {
  await mockAgent(page);
  await emit(page, 0, "tool_started", { callId: "cancel-tool", name: "check_source", argsPreview: "Checking evidence" });
  await emit(page, 1, "text", { text: "A partial answer remains readable." });
  await emit(page, 2, "failed", { message: "Response stopped", code: "CANCELLED" });
  await expect(page.getByTestId("chat-part-text")).toContainText("A partial answer remains readable.");
  await expect(page.getByTestId("chat-part-tool")).toContainText("Failed");
  await expect(page.getByTestId("chat-stream-caret")).toHaveCount(0);
  await expect(page.getByTestId("chat-agent-activity").locator(".lucide-loader-circle")).toHaveCount(0);
});
