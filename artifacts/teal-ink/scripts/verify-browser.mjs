import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { extname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { root } from "./token-tools.mjs";

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}
const kitPath = fileURLToPath(root);
const require = createRequire(pathToFileURL(resolve(option("--modules-from", resolve(kitPath, "package.json")))));
const { chromium, expect } = require("@playwright/test");
const evidencePath = resolve(option("--evidence", resolve(kitPath, "evidence")));
await mkdir(evidencePath, { recursive: true });
const mime = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json", ".woff2": "font/woff2", ".md": "text/plain; charset=utf-8" };
const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
    const path = resolve(kitPath, `.${pathname === "/" ? "/preview.html" : pathname}`);
    const inside = relative(kitPath, path);
    if (inside.startsWith("..") || isAbsolute(inside) || !(await stat(path)).isFile()) throw new Error("Not found");
    response.writeHead(200, { "Content-Type": mime[extname(path)] ?? "application/octet-stream" });
    response.end(await readFile(path));
  } catch {
    response.writeHead(404);
    response.end("Not found");
  }
});
await new Promise((done) => server.listen(0, "127.0.0.1", done));
const origin = `http://127.0.0.1:${server.address().port}`;
const report = { timestamp: new Date().toISOString(), browser: "Chromium", layouts: [], accessibility: [], toneContrast: [], checks: [], errors: [], externalRequests: [] };
let browser;

async function layout(page, label) {
  const result = await page.evaluate(() => ({ viewport: innerWidth, width: document.documentElement.scrollWidth, body: getComputedStyle(document.body).backgroundColor }));
  report.layouts.push({ label, ...result });
  assert.ok(result.width <= result.viewport + 1, `${label}: page overflow ${result.width} > ${result.viewport}`);
}

async function setLanguage(page, lang) {
  if (await page.locator("html").getAttribute("lang") !== lang) await page.locator("#language-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("lang", lang);
}

try {
  browser = await chromium.launch({ headless: true });
  report.browserVersion = browser.version();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark", reducedMotion: "reduce", permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  page.on("pageerror", (error) => report.errors.push(error.message));
  page.on("request", (request) => { if (!request.url().startsWith(origin) && !request.url().startsWith("data:")) report.externalRequests.push(request.url()); });
  await page.goto(origin);
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator(".preview-swatch")).toHaveCount(5);
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  for (const theme of ["light", "dark"]) {
    await page.locator("#theme-choice").selectOption(theme);
    const tones = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      const rgb = (value) => { context.clearRect(0, 0, 1, 1); context.fillStyle = value; context.fillRect(0, 0, 1, 1); return [...context.getImageData(0, 0, 1, 1).data].slice(0, 3); };
      const luminance = (color) => { const channels = color.map((part) => { const value = part / 255; return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4; }); return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2]; };
      return [...document.querySelectorAll(".ti-badge")].map((badge) => {
        const style = getComputedStyle(badge);
        const values = [luminance(rgb(style.color)), luminance(rgb(style.backgroundColor))].sort((a, b) => b - a);
        return { tone: badge.dataset.tone ?? "neutral", ratio: (values[0] + .05) / (values[1] + .05) };
      });
    });
    report.toneContrast.push({ theme, tones });
    assert.ok(tones.every((tone) => tone.ratio >= 4.5), `${theme} tone contrast: ${JSON.stringify(tones.filter((tone) => tone.ratio < 4.5))}`);
    for (const language of ["en", "zh-CN"]) {
      await setLanguage(page, language);
      for (const width of [320, 390, 768, 1024, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        await layout(page, `${theme}/${language}/${width}`);
        if (width === 320 || width === 1440) {
          const result = await page.evaluate(async () => {
            const result = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "best-practice"] } });
            return { violations: result.violations.map((violation) => ({ id: violation.id, impact: violation.impact, nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })) })), incomplete: result.incomplete.map((rule) => rule.id) };
          });
          report.accessibility.push({ theme, language, width, ...result });
        }
      }
    }
  }
  const violations = report.accessibility.flatMap((audit) => audit.violations.map((violation) => ({ theme: audit.theme, language: audit.language, width: audit.width, ...violation })));
  assert.equal(violations.length, 0, JSON.stringify(violations, null, 2));
  console.log("PASS 20 responsive/theme/locale layouts and 8 axe audits");

  for (const theme of ["light", "dark"]) {
    await page.locator("#theme-choice").selectOption(theme);
    for (const language of ["en", "zh-CN"]) {
      await setLanguage(page, language);
      for (const width of [320, 768, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
        await layout(page, `200%/${theme}/${language}/${width}`);
        await page.evaluate(() => { document.documentElement.style.fontSize = ""; });
      }
    }
  }
  report.checks.push("200% root text across 12 viewport/theme/locale combinations");

  await page.setViewportSize({ width: 1440, height: 1000 });
  await setLanguage(page, "en");
  await page.locator("#theme-choice").selectOption("light");
  const lightBackground = await page.locator("body").evaluate((node) => getComputedStyle(node).backgroundColor);
  assert.equal(lightBackground, "rgb(246, 248, 251)");
  await page.locator("#theme-choice").selectOption("dark");
  assert.equal(await page.locator("body").evaluate((node) => getComputedStyle(node).backgroundColor), "rgb(18, 20, 22)");
  const gateway = await page.locator(".preview-gateway .ti-button").evaluate((node) => getComputedStyle(node).backgroundColor);
  assert.equal(gateway, "rgb(164, 236, 220)");
  const nested = await page.evaluate(() => {
    const boundary = document.createElement("div");
    boundary.className = "ti-root";
    boundary.dataset.tiTheme = "light";
    boundary.innerHTML = '<button class="ti-button" type="button">Nested</button>';
    document.body.append(boundary);
    const result = getComputedStyle(boundary.firstElementChild).backgroundColor;
    boundary.remove();
    return result;
  });
  assert.equal(nested, "rgb(8, 112, 138)");
  report.checks.push("Exact light/dark source backgrounds, gateway mint, and nested light component aliases");
  await page.locator("#theme-choice").selectOption("system");
  await page.emulateMedia({ colorScheme: "light" });
  assert.equal(await page.locator("body").evaluate((node) => getComputedStyle(node).backgroundColor), "rgb(246, 248, 251)");
  await page.emulateMedia({ colorScheme: "dark" });
  assert.equal(await page.locator("body").evaluate((node) => getComputedStyle(node).backgroundColor), "rgb(18, 20, 22)");
  await page.locator("#theme-choice").selectOption("light");
  await page.reload();
  await expect(page.locator("#theme-choice")).toHaveValue("light");
  report.checks.push("System preference changes and theme persistence");

  await page.locator("#project-name").fill("");
  await page.locator("#example-form button[type=submit]").click();
  await expect(page.locator("#project-name")).toBeFocused();
  await expect(page.locator("#project-name")).toHaveAttribute("aria-invalid", "true");
  await expect(page.locator("#project-error")).toBeVisible();
  await page.locator("#project-name").fill("A reusable workspace");
  await page.locator("#example-form button[type=submit]").click();
  await expect(page.locator("#project-error")).toBeHidden();
  await expect(page.locator("#preview-status")).toContainText("saved");
  report.checks.push("Form error association, first-error focus, and successful local example");

  const opener = page.locator("[data-open-review]").first();
  await opener.click();
  await expect(page.locator("#review-dialog")).toBeVisible();
  for (let index = 0; index < 4; index++) {
    await page.keyboard.press("Tab");
    // Chromium can tab into browser chrome; this leaves BODY active while the
    // document has no focus. No background application control may receive it.
    assert.ok(await page.evaluate(() => document.querySelector("#review-dialog").contains(document.activeElement) || (!document.hasFocus() && document.activeElement === document.body)), "Dialog focus escaped into background content");
  }
  await opener.evaluate((node) => node.focus());
  assert.ok(await page.evaluate(() => document.querySelector("#review-dialog").contains(document.activeElement)), "Modal background was not inert");
  await page.keyboard.press("Escape");
  await expect(page.locator("#review-dialog")).not.toBeVisible();
  await expect(opener).toBeFocused();
  await opener.click();
  await page.locator('#review-dialog button[value="confirm"]').click();
  await expect(page.locator("#preview-status")).toContainText("confirmed");
  await opener.click();
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#review-dialog").evaluate((node) => node.returnValue), "");
  report.checks.push("Native dialog focus containment, Escape, focus return, confirmation, and stale-result reset");

  await page.locator("#load-demo").click();
  await expect(page.locator("#load-demo")).toBeDisabled();
  await expect(page.locator("#load-demo")).toHaveAttribute("aria-busy", "true");
  await expect(page.locator("#load-demo")).toBeEnabled({ timeout: 4000 });
  await page.locator("#token-search").fill("component.button.bg");
  await expect(page.locator("#token-results tr")).toHaveCount(1);
  await page.locator("#token-results button").click();
  await expect(page.locator("#preview-status")).toContainText("Copied");
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), "var(--ti-button-bg)");
  await page.locator("#token-search").fill("no-such-token-for-this-check");
  await expect(page.locator("#token-empty")).toBeVisible();
  await page.locator("#token-search").fill("");
  report.checks.push("Loading admission, token search, clipboard contents, and empty search state");

  await page.emulateMedia({ reducedMotion: "reduce" });
  assert.equal(await page.locator(".ti-spinner").first().evaluate((node) => getComputedStyle(node).animationName), "none");
  assert.equal(await page.locator(".ti-button").first().evaluate((node) => getComputedStyle(node).transitionDuration), "0s");
  await page.emulateMedia({ forcedColors: "active" });
  await layout(page, "forced-colors");
  await page.emulateMedia({ forcedColors: "none" });
  report.checks.push("Reduced-motion animation/transition removal and forced-colors layout");

  await page.goto(origin);
  await page.keyboard.press("Tab");
  await expect(page.locator(".ti-skip-link")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  report.checks.push("Keyboard skip link");

  const touch = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, reducedMotion: "reduce" });
  const touchPage = await touch.newPage();
  await touchPage.goto(origin);
  const targets = await touchPage.locator('.ti-button:not([disabled]), .ti-nav-item, .ti-input, .ti-select').evaluateAll((nodes) => nodes.filter((node) => node.getBoundingClientRect().height > 0).map((node) => ({ label: node.textContent.slice(0, 25), height: node.getBoundingClientRect().height })));
  assert.ok(targets.every((target) => target.height >= 44), JSON.stringify(targets.filter((target) => target.height < 44)));
  report.checks.push(`Coarse-pointer minimum height for ${targets.length} visible controls`);
  await touch.close();

  await page.setViewportSize({ width: 1440, height: 1000 });
  for (const theme of ["light", "dark"]) {
    await page.locator("#theme-choice").selectOption(theme);
    await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: resolve(evidencePath, `overview-${theme}.png`) });
    await page.screenshot({ path: resolve(evidencePath, `desktop-${theme}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await setLanguage(page, "zh-CN");
  await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: resolve(evidencePath, "overview-mobile-dark-zh.png") });
  await page.screenshot({ path: resolve(evidencePath, "mobile-dark-zh.png"), fullPage: true });

  const filePage = await context.newPage();
  const fileErrors = [];
  filePage.on("pageerror", (error) => fileErrors.push(error.message));
  await filePage.goto(pathToFileURL(resolve(kitPath, "preview.html")).href);
  await expect(filePage.locator(".preview-swatch")).toHaveCount(5);
  await filePage.locator("#theme-choice").selectOption("light");
  await filePage.locator("#token-search").fill("component.button.bg");
  await expect(filePage.locator("#token-results tr")).toHaveCount(1);
  assert.deepEqual(fileErrors, []);
  report.checks.push("Direct file:// offline preview, theme switching, and token search");
  assert.deepEqual(report.errors, []);
  assert.deepEqual(report.externalRequests, []);
  report.status = "pass";
  console.log(`PASS ${report.layouts.length} layouts, ${report.accessibility.length} axe audits, ${report.checks.length} interaction/environment checks; zero page errors or external requests.`);
} catch (error) {
  report.status = "fail";
  report.failure = error.stack;
  console.error(error);
  process.exitCode = 1;
} finally {
  await writeFile(resolve(evidencePath, "browser-report.json"), JSON.stringify(report, null, 2) + "\n");
  await browser?.close();
  await new Promise((done) => server.close(done));
  console.log(`Evidence: ${evidencePath}`);
}
