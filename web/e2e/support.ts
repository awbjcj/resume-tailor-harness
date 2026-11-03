import type { Page } from "@playwright/test";

export async function mockGmailSettings(page: Page) {
  await page.route("**/api/mailboxes", (route) => route.fulfill({ json: { providers: [], accounts: [] } }));
  await page.route("**/api/gmail/status", (route) => route.fulfill({ json: {
    connected: true, scopes: [], draftCapable: true, clientSource: "platform",
  } }));
  await page.route("**/api/secrets", (route) => route.fulfill({ json: [
    { key: "openaiApiKey", isSet: false, hint: null },
    { key: "googleOauthClientId", isSet: false, hint: null },
    { key: "googleOauthClientSecret", isSet: false, hint: null },
  ] }));
}

export async function mockEmptyRuns(page: Page) {
  await page.route("**/api/run-completions?*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/board-views?*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/workspace-agent/proposals?*", (route) =>
    route.fulfill({ json: { proposals: [], nextOffset: null } }));
  await page.route("**/api/config/language", async (route) => route.fulfill({ json: route.request().postDataJSON() }));
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: { username: null, role: null, authRequired: false },
    }));
  await page.route("**/api/runs?*", (route) =>
    route.fulfill({
      json: {
        data: [],
        pagination: { page: 1, pageSize: 200, totalItems: 0, totalPages: 0 },
      },
    }));
  await page.route("**/api/interview/sessions*", (route) =>
    route.fulfill({ json: [] }),
  );
}
