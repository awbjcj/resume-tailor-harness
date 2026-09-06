import { test, expect } from "@playwright/test";
import { mockEmptyRuns } from "./support";

for (const width of [390, 1280]) {
  test(`public page corrections and approval at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockEmptyRuns(page);
    await page.route("**/api/run-completions", (route) =>
      route.fulfill({ json: [] }),
    );
    await page.route("**/api/notifications", (route) =>
      route.fulfill({ json: [] }),
    );
    await page.route("**/api/sources", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/setup/status", (route) =>
      route.fulfill({
        json: {
          complete: true,
          secrets: { anyLlmKey: true },
          profile: { documentCount: 1, hasResume: true },
          search: { configured: true },
          sources: { enabledCount: 1 },
        },
      }),
    );
    let draft = {
      id: "draft",
      sourceId: "board",
      url: "https://example.com/jobs",
      revision: 0,
      state: "validated",
      validation: { valid: true },
      limits: { listingPages: 10, detailPages: 50, elapsedSeconds: 300 },
      plan: {
        cardSelector: "article",
        linkSelector: "a",
        detailMode: "link",
        detailSelector: ".jd",
        fieldRules: [],
      },
      samples: [
        {
          id: "sample",
          jobKey: "one",
          sourceId: "board",
          revision: 0,
          accepted: true,
          facts: {
            title: "Engineer",
            company: "Example",
            jdText: "Build reliable public services.",
            sourceUrl: "https://example.com/one",
            remotePolicy: "remote" as string | null,
          },
          evidence: [],
        },
      ],
    };
    let approved = false;
    await page.route("**/api/scrape/sources", (route) =>
      route.fulfill({ json: [{ ...draft, state: "approved", revision: 1 }] }),
    );
    await page.route("**/api/scrape/sources/board/edit", (route) =>
      route.fulfill({ json: draft }),
    );
    await page.route("**/api/scrape/drafts/draft", async (route) => {
      if (route.request().method() === "PATCH") {
        const body = route.request().postDataJSON();
        draft = {
          ...draft,
          revision: 1,
          samples: [{ ...draft.samples[0], facts: body.samples.one }],
        };
      }
      await route.fulfill({ json: draft });
    });
    await page.route("**/api/scrape/drafts/draft/approve", async (route) => {
      expect(draft.samples[0].facts.title).toBe("Reviewed engineer");
      expect(draft.samples[0].facts.remotePolicy).toBeNull();
      approved = true;
      await route.fulfill({
        json: { sourceId: "board", approvedRevision: 2, jobIds: [1] },
      });
    });
    await page.goto("/sources");
    await page.getByRole("button", { name: "Edit or relearn" }).click();
    await page.getByLabel("Title", { exact: true }).fill("Reviewed engineer");
    await page
      .getByRole("combobox", { name: "Work policy", exact: true })
      .selectOption("");
    await expect(page.getByLabel("Full description")).toHaveValue(
      "Build reliable public services.",
    );
    const dialog = page.getByRole("dialog");
    expect(
      await dialog.evaluate((node) => node.scrollWidth <= node.clientWidth + 1),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/public-review-${width}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "Approve and save" }).click();
    await expect(dialog).toBeHidden();
    expect(approved).toBe(true);
  });
}
