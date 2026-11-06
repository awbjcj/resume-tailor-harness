import { expect, test } from "@playwright/test";

import { mockEmptyRuns, PROVIDER_SETUP } from "./support";

const INCOMPLETE_STATUS = {
  secrets: { anthropicKey: false, anyLlmKey: false },
  profile: { documentCount: 0, hasResume: false, factsBuiltAt: null, githubUsername: null },
  search: { configured: false },
  sources: { enabledCount: 0 },
  complete: false,
};

// Hermetic smoke: intercept the API so no backend is required, matching the
// pattern in e2e/smoke.spec.ts and e2e/sources.spec.ts.
test.beforeEach(async ({ page }) => {
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: INCOMPLETE_STATUS }));
  await page.route("**/api/setup/provider", (route) => route.fulfill({ json: PROVIDER_SETUP }));
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await mockEmptyRuns(page);
  await page.route("**/api/dashboard/summary", (route) =>
    route.fulfill({
      json: {
        statusCounts: {},
        queues: { triage: 0, approve: 0, tailor: 0, apply: 0 },
        applied: 0,
      },
    }));
  await page.route("**/api/secrets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profile/documents", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/config/profile", (route) =>
    route.fulfill({ json: { githubUsername: null } }));
  await page.route("**/api/config/search", (route) =>
    route.fulfill({
      json: {
        keywords: [], titles: [], locations: [], remotePolicy: [],
        minSalary: null, yoeMin: null, yoeMax: null, sponsorshipRequired: false,
        roleAnchors: [], excludeTerms: [], targetRole: null,
        distance: null, maxDaysOld: null, experienceLevels: [], employmentTypes: [],
      },
    }));
});

test("first run gates to the wizard; exit reaches the app; settings nav works", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/setup/);
  await expect(page.getByText("First-run setup")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose an AI provider" })).toBeVisible();

  await page.getByRole("button", { name: "Exit setup" }).click();
  await expect(page).not.toHaveURL(/\/setup/);

  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/settings\/search$/);
  await page.getByRole("link", { name: "Search" }).click();
  await expect(page.getByLabel("Keywords", { exact: true })).toBeVisible();
});

test("a named provider can be set up with a single key", async ({ page }) => {
  let payload: unknown;
  await page.route("**/api/setup/provider", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: PROVIDER_SETUP });
    payload = route.request().postDataJSON();
    return route.fulfill({ status: 204 });
  });
  await page.goto("/setup/keys");
  const provider = page.getByLabel("AI provider", { exact: true });
  await expect(provider).toHaveValue("openai");
  await page.getByLabel("API key", { exact: true }).fill("test-openai-key");
  await provider.selectOption("gemini");
  const key = page.getByLabel("API key", { exact: true });
  await expect(key).toHaveValue("");
  await expect(page.getByLabel("API base URL")).toHaveCount(0);
  await key.fill("test-gemini-key");
  await page.getByRole("button", { name: "Save & continue" }).click();
  await expect(page).toHaveURL(/\/setup\/documents$/);
  await expect(page.getByRole("main")).toBeFocused();
  expect(payload).toEqual({ provider: "gemini", apiKey: "test-gemini-key" });
});

test("a local custom endpoint retains its draft after validation fails", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await page.addInitScript(() => localStorage.setItem("resume-tailor-harness-language", "zh-CN"));
  const attempts: unknown[] = [];
  await page.route("**/api/setup/provider", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: PROVIDER_SETUP });
    attempts.push(route.request().postDataJSON());
    return attempts.length === 1
      ? route.fulfill({ status: 422, json: { error: { code: "INVALID_BASE_URL" } } })
      : route.fulfill({ status: 204 });
  });

  await page.goto("/setup/keys");
  await page.getByRole("checkbox", { name: "使用自定义 API 端点" }).check();
  await expect(page.getByLabel("API 格式")).toHaveValue("openai");
  const url = page.getByLabel("API 基础网址");
  await url.fill("wrong-url");
  await page.getByLabel("模型 ID").fill("vendor/model");
  const key = page.getByLabel("API 密钥", { exact: true });
  await key.fill("test-custom-key");
  await expect(key).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "显示 API 密钥" }).click();
  await expect(key).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "隐藏 API 密钥" }).click();
  await page.getByRole("button", { name: "保存并继续" }).click();
  await expect(url).toBeFocused();
  await expect(url).toHaveAttribute("aria-invalid", "true");
  await expect(key).toHaveValue("test-custom-key");
  await page.getByLabel("模型 ID").fill("vendor/revised-model");
  await expect(url).toHaveAttribute("aria-invalid", "true");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  await url.fill("http://127.0.0.1:9001/v1");
  await page.getByRole("button", { name: "保存并继续" }).click();
  await expect(page).toHaveURL(/\/setup\/documents$/);
  expect(attempts[1]).toEqual({
    provider: "openai", baseUrl: "http://127.0.0.1:9001/v1", modelId: "vendor/revised-model", apiKey: "test-custom-key",
  });
});

test("saving announces progress without moving the setup actions", async ({ page }) => {
  let finishSave!: () => void;
  let finishRefresh!: () => void;
  const saved = new Promise<void>((resolve) => { finishSave = resolve; });
  const refreshed = new Promise<void>((resolve) => { finishRefresh = resolve; });
  let savedProvider = false;
  await page.route("**/api/setup/provider", async (route) => {
    if (route.request().method() === "GET") {
      if (savedProvider) await refreshed;
      return route.fulfill({ json: PROVIDER_SETUP });
    }
    await saved;
    savedProvider = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/setup/keys");
  await page.getByLabel("API key", { exact: true }).fill("test-openai-key");
  const skip = page.getByRole("button", { name: "Skip for now" });
  const submit = page.getByRole("button", { name: "Save & continue" });
  const before = await skip.boundingBox();
  try {
    await submit.press("Enter");
    await expect(page.getByRole("button", { name: "Saving…" })).toBeDisabled();
    await expect(page.getByRole("status").filter({ hasText: "Saving…" })).toHaveCount(1);
    expect(await skip.boundingBox()).toEqual(before);
    finishSave();
    await expect(page).toHaveURL(/\/setup\/documents$/);
  } finally {
    finishSave();
    finishRefresh();
  }
});

test("the provider form keeps an inactive saved custom connection off", async ({ page }) => {
  await page.route("**/api/setup/provider", (route) => route.fulfill({ json: {
    ...PROVIDER_SETUP,
    providers: [{ id: "openai", label: "OpenAI", available: true }],
    modelTiersReady: true,
    customEndpoint: { provider: "openai", baseUrl: "https://endpoint.example/v2", modelId: "proxy-model", selected: false },
  } }));
  await page.goto("/setup/keys");
  const toggle = page.getByRole("checkbox", { name: "Use a custom API endpoint" });
  await expect(toggle).not.toBeChecked();
  await expect(page.getByLabel("API base URL")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeVisible();
  await toggle.check();
  await expect(page.getByLabel("API base URL")).toHaveValue("https://endpoint.example/v2");
  await expect(page.getByLabel("API key (optional)")).toHaveValue("");
});
