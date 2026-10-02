import { createRequire } from "node:module";
import { expect, test } from "@playwright/test";

import { mockEmptyRuns } from "./support";

const require = createRequire(import.meta.url);
const offers = [
  { priceId: "price_credit", name: "Credit top-up", mode: "payment", amountCents: 1000, currency: "usd", creditMicros: 10_000_000 },
  { priceId: "price_plan", name: "Subscriber", mode: "subscription", amountCents: 2000, currency: "usd", tierId: "SUBSCRIBER", allowanceMicros: 20_000_000, interval: "month", intervalCount: 1 },
];
const quota = {
  tierId: "FREE", tierName: "Free", creditBalanceMicros: 4_500_000,
  recurringAllowanceMicros: 1_000_000, allowanceOverrideMicros: null,
  spendMicros: 200_000, remainingMicros: 5_300_000, overageMicros: 0,
  periodStart: "2026-10-01T00:00:00Z", periodEnd: "2026-10-08T00:00:00Z",
  nextResetAt: "2026-10-08T00:00:00Z", enforcementStatus: "ACTIVE",
};

test.use({ locale: "en-US", reducedMotion: "reduce" });
test.beforeEach(async ({ page }) => {
  await mockEmptyRuns(page);
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { username: "alice", email: "alice@example.com", emailVerified: true, needsEmail: false, role: "user", authRequired: true, googleLinked: false } }));
  await page.route("**/api/account/usage", (route) => route.fulfill({ json: { weightedTotal: 0, ownKeyWeightedTotal: 0, budget: 0, quota } }));
  await page.route("**/api/account/tokens", (route) => route.fulfill({ json: { tokens: [] } }));
  await page.route("**/api/account/billing", (route) => route.fulfill({ json: { enabled: true, offers, portalAvailable: false } }));
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/run-completions*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/errors?*", (route) => route.fulfill({ json: { records: [] } }));
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: { secrets: { anyLlmKey: true }, profile: { documentCount: 1, hasResume: true, factsBuiltAt: "2026-10-01T00:00:00Z" }, search: { configured: true }, sources: { enabledCount: 1 }, complete: true } }));
});

for (const theme of ["light", "dark"] as const) {
  for (const viewport of [{ name: "desktop", width: 1280, height: 960 }, { name: "mobile", width: 375, height: 812 }, { name: "landscape", width: 812, height: 375 }]) {
    test(`billing is accessible and contained on ${viewport.name} in ${theme} mode`, async ({ page }, testInfo) => {
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.addInitScript((value) => { localStorage.setItem("theme", value); localStorage.setItem("resume-tailor-harness-language", "en"); }, theme);
      await page.goto("/account");
      const panel = page.getByRole("region", { name: "Plans and credits" });
      await expect(panel).toBeVisible();
      await expect(panel.getByText("$4.50", { exact: true })).toBeVisible();
      const credit = panel.getByRole("button", { name: "Add credit for $10.00" });
      const plan = panel.getByRole("button", { name: "Subscribe to Subscriber" });
      await expect(credit).toBeVisible();
      await expect(plan).toBeVisible();
      expect(await panel.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      expect((await credit.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await credit.focus();
      await page.keyboard.press("Tab");
      await expect(plan).toBeFocused();
      const planBounds = (await plan.boundingBox())!;
      const chromeBounds = (await page.locator("header.app-chrome").boundingBox())!;
      expect(planBounds.y).toBeGreaterThanOrEqual(chromeBounds.y + chromeBounds.height);
      expect(planBounds.y + planBounds.height).toBeLessThanOrEqual(viewport.height);
      await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
      const violations = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: { run: (selector: string) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
        return (await axe.run('section[aria-labelledby="account-billing"]')).violations.map(({ id, impact }) => ({ id, impact }));
      });
      expect(violations).toEqual([]);
      // Capture the entire panel without fixed page chrome covering a stitched
      // screenshot. Keyboard visibility above is checked in the real layout.
      await plan.evaluate((element) => element.blur());
      await page.addStyleTag({ content: 'header.app-chrome { position: static !important; } a[href="#main-content"] { visibility: hidden !important; }' });
      await panel.screenshot({ path: testInfo.outputPath(`billing-${viewport.name}-${theme}.png`) });
    });
  }
}
