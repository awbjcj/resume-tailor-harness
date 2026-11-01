import { expect, test } from "@playwright/test";

import { mockEmptyRuns } from "./support";

const setupStatus = {
  secrets: { anthropicKey: true, anyLlmKey: true },
  profile: {
    documentCount: 2,
    hasResume: true,
    factsBuiltAt: "2026-07-10T00:00:00Z",
    githubUsername: "octocat",
  },
  search: { configured: true },
  sources: { enabledCount: 1 },
  complete: true,
};

test.beforeEach(async ({ page }) => {
  let pythonGroup = "languages";
  let pythonGroupSource = "taxonomy";
  let addedSkill: string | null = null;
  await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: setupStatus }));
  await mockEmptyRuns(page);
  await page.route("**/api/run-completions?*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profile/sources/github-exclusions", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profile/skeleton", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profile/suppressed-skills", (route) =>
    route.fulfill({ json: [] }));
  await page.route("**/api/profile/coach/sessions", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profile/sources", (route) =>
    route.fulfill({
      json: [
        {
          id: "resume",
          filename: "resume.pdf",
          mode: "literal",
          origin: "upload",
          primary: true,
          anchor: null,
          addedAt: "2026-07-10T00:00:00Z",
          fragmentStatus: "cached",
        },
        {
          id: "github-repo",
          filename: "github--portfolio.md",
          mode: "project",
          origin: "github",
          primary: false,
          anchor: null,
          addedAt: "2026-07-10T00:00:00Z",
          fragmentStatus: "cached",
          repoUrl: "https://github.com/octocat/portfolio",
          githubBranch: "main",
        },
      ],
    }));
  await page.route("**/api/profile/matrix", (route) =>
    route.fulfill({
      json: {
        generatedAt: "2026-07-10T00:00:00Z",
        groups: [
          { slug: "languages", label: "Languages" },
          { slug: "other", label: "Other" },
        ],
        rows: [
          {
            key: "python",
            display: "Python",
            category: "hard",
            group: pythonGroup,
            groupSource: pythonGroupSource,
            inferred: false,
            strength: 3,
            lastUsed: "current",
          },
          {
            key: "vflash",
            display: "vFlash",
            category: "hard",
            group: null,
            inferred: false,
            strength: 1,
            lastUsed: null,
          },
          ...(addedSkill
            ? [{
                key: addedSkill.toLowerCase(),
                display: addedSkill,
                category: "hard",
                group: "languages",
                groupSource: "correction",
                inferred: false,
                strength: 0,
                lastUsed: null,
              }]
            : []),
        ],
      },
    }));
  await page.route("**/api/profile/skills", async (route) => {
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON();
      addedSkill = payload.name;
      await route.fulfill({
        status: 201,
        json: {
          id: "manual-skill",
          kind: "new_skill",
          addedAt: "2026-07-10T00:00:00Z",
          name: addedSkill,
          category: payload.category,
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/profile/skills/*/group", async (route) => {
    if (route.request().method() === "PUT") {
      pythonGroup = route.request().postDataJSON().group;
      pythonGroupSource = "correction";
      await route.fulfill({
        json: {
          key: "python",
          display: "Python",
          category: "hard",
          group: pythonGroup,
          groupSource: pythonGroupSource,
          inferred: false,
          strength: 3,
          lastUsed: "current",
        },
      });
      return;
    }
    pythonGroup = "languages";
    pythonGroupSource = "taxonomy";
    await route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/config/profile", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({ json: route.request().postDataJSON() });
      return;
    }
    await route.fulfill({
      json: {
        githubUsername: "octocat",
        githubRepoAllow: [],
        githubRepoDeny: [],
        githubRepoLimit: 20,
      },
    });
  });
  await page.route("**/api/profile/sources/note", (route) =>
    route.fulfill({
      status: 201,
      json: {
        id: "note",
        filename: "note--on-call.md",
        mode: "literal",
        origin: "upload",
        primary: false,
        anchor: null,
        addedAt: "2026-07-10T00:00:00Z",
        fragmentStatus: "missing",
      },
    }));
});

test("profile depth controls and grouped skills form one working story", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/profile");
  await expect(page.getByRole("heading", { name: "Profile", exact: true })).toBeVisible();
  // Documents is the default tab — sources + repo controls live here.
  await expect(page.getByRole("article", { name: /github--portfolio\.md/i })).toContainText("GitHub");
  await expect(page.getByLabel("mode for github--portfolio.md")).toHaveCount(0);

  await page.getByRole("button", { name: "Add note" }).click();
  await page.getByLabel("Note title").fill("On-call");
  await page.getByLabel("Note text").fill("Led the rotation.");
  const noteRequest = page.waitForRequest(
    (request) => request.url().endsWith("/api/profile/sources/note") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Save note" }).click();
  expect((await noteRequest).postDataJSON()).toEqual({ title: "On-call", text: "Led the rotation." });
  await expect(page.getByRole("dialog", { name: "Add a note" })).toHaveCount(0);

  await page.getByText("Import preferences", { exact: true }).click();
  await page.getByLabel("Always include repositories").fill("portfolio, flagship");
  await page.getByLabel("Exclude repositories").fill("archive");
  await page.getByLabel("Repository limit").fill("5");
  const saveRequest = page.waitForRequest(
    (request) => request.url().endsWith("/api/config/profile") && request.method() === "PUT",
  );
  await page.getByRole("button", { name: "Save changes" }).click();
  expect((await saveRequest).postDataJSON()).toMatchObject({
    githubRepoAllow: ["portfolio", "flagship"],
    githubRepoDeny: ["archive"],
    githubRepoLimit: 5,
  });
  await expect(page.getByRole("button", { name: "Save changes" })).toHaveCount(0);

  // Skills are behind their own tab now, no longer stacked under Documents.
  await page.getByRole("tab", { name: "Skills" }).click();
  await expect(page.getByRole("heading", { name: "Skill groups" })).toBeVisible();
  await expect(page.getByText("Python", { exact: true })).toBeVisible();
  await expect(page.getByText("vFlash", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Add skill" }).first().click();
  await page.getByLabel("Skill name").fill("TypeScript");
  const addRequest = page.waitForRequest(
    (request) => request.url().endsWith("/api/profile/skills") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Add to category" }).click();
  expect((await addRequest).postDataJSON()).toEqual({ name: "TypeScript", category: null });

  const moveRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/profile/skills/python/group") &&
      request.method() === "PUT",
  );
  await page.getByRole("button", { name: "Change group for Python" }).click();
  await page.getByRole("menuitem", { name: "Other", exact: true }).click();
  expect((await moveRequest).postDataJSON()).toEqual({ group: "other" });
  const pinnedTrigger = page.getByRole("button", { name: "Change group for Python" });
  await expect(pinnedTrigger.locator('[data-icon="inline-start"]')).toBeVisible();

  const resetRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/profile/skills/python/group") &&
      request.method() === "DELETE",
  );
  await pinnedTrigger.click();
  await page.getByRole("menuitem", { name: "Reset to automatic" }).click();
  await resetRequest;
  await expect(
    page.getByRole("button", { name: "Change group for Python" }).locator(
      '[data-icon="inline-start"]',
    ),
  ).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("profile settings stay contained at a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/profile");
  await page.getByRole("tab", { name: "Skills" }).click();
  await expect(page.getByRole("heading", { name: "Skill groups" })).toBeVisible();

  const layout = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(layout.document).toBeLessThanOrEqual(layout.viewport);

  await page.getByRole("tab", { name: "Documents" }).click();
  await page.getByRole("button", { name: "Add URL", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Add a public page" });
  await expect(dialog).toBeVisible();
  const bounds = await dialog.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(320);
});

test("source files can be replaced and removed without losing their roles", async ({ page }) => {
  let rows = [
    { id: "resume", filename: "resume.pdf", mode: "literal", primary: true,
      origin: "upload", anchor: null, addedAt: "2026-07-10", fragmentStatus: "cached", fileExists: true },
    { id: "github-repo", filename: "github--portfolio.md", mode: "project", primary: false,
      origin: "github", anchor: null, addedAt: "2026-07-10", fragmentStatus: "missing", fileExists: true },
  ];
  let excluded: string[] = [];
  await page.route("**/api/profile/sources", (route) => route.fulfill({ json: rows }));
  await page.route("**/api/profile/sources/github-exclusions", async (route) => {
    if (route.request().method() === "DELETE") {
      excluded = [];
      await route.fulfill({ status: 204 });
    } else await route.fulfill({ json: excluded });
  });
  await page.route("**/api/profile/sources/*/file", async (route) => {
    const id = route.request().url().split("/").at(-2);
    const body = route.request().postData() ?? "";
    expect(body).not.toContain('name="primary"');
    expect(body).not.toContain('name="mode"');
    rows = rows.map((row) => row.id === id
      ? { ...row, filename: id === "resume" ? "new-resume.pdf" : "updated-dossier.md",
          origin: "upload", fragmentStatus: "missing" }
      : row);
    await route.fulfill({ json: rows.find((row) => row.id === id) });
  });
  await page.route(/\/api\/profile\/sources\/github-repo\?purge=true$/, async (route) => {
    rows = rows.filter((row) => row.id !== "github-repo");
    excluded = ["updated-dossier.md"];
    await route.fulfill({ status: 204 });
  });

  await page.goto("/profile");
  const githubRow = page.getByRole("article", { name: /github--portfolio\.md/i });
  await expect(githubRow).toContainText("Needs build");
  await expect(githubRow).not.toContainText("File missing");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Replace github--portfolio.md" }).click();
  await (await chooser).setFiles({ name: "updated-dossier.md", mimeType: "text/markdown", buffer: Buffer.from("# Updated evidence") });
  await expect(page.getByRole("article", { name: /updated-dossier\.md/i })).toContainText("Project");
  await expect(page.getByRole("article", { name: /resume\.pdf/i })).toContainText("Primary");

  const resumeChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Replace resume.pdf" }).click();
  await (await resumeChooser).setFiles({ name: "new-resume.pdf", mimeType: "application/pdf", buffer: Buffer.from("new resume") });
  await expect(page.getByRole("article", { name: /new-resume\.pdf/i })).toContainText("Primary");
  await page.getByRole("button", { name: "Remove updated-dossier.md" }).click();
  await page.getByRole("button", { name: "Remove source", exact: true }).click();
  await expect(page.getByRole("article", { name: /updated-dossier\.md/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Restore removed GitHub sources" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("article", { name: /updated-dossier\.md/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Restore removed GitHub sources" }).click();
  await expect(page.getByRole("button", { name: "Restore removed GitHub sources" })).toHaveCount(0);
});

test("repository branch choices are saved and survive reload", async ({ page }) => {
  let config = { githubUsername: "octocat", githubRepoAllow: [], githubRepoDeny: [], githubRepoLimit: 20,
    githubRepoBranches: {} as Record<string, string> };
  await page.route("**/api/config/profile", async (route) => {
    if (route.request().method() === "PUT") config = route.request().postDataJSON();
    await route.fulfill({ json: config });
  });
  await page.route("**/api/profile/github/repositories", (route) => route.fulfill({ json: [
    { owner: "octocat", name: "portfolio", fullName: "octocat/portfolio", defaultBranch: "main", included: true,
      selectedBranch: config.githubRepoBranches["octocat/portfolio"] ?? null },
  ] }));
  await page.route("**/api/profile/github/repositories/octocat/portfolio/branches", (route) =>
    route.fulfill({ json: ["main", "dev", "feature/dossier"] }));

  await page.goto("/profile");
  await page.getByRole("button", { name: "Choose repository branches" }).click();
  const branch = page.getByRole("combobox", { name: "Branch for octocat/portfolio" });
  await branch.click();
  await page.getByRole("option", { name: "feature/dossier", exact: true }).click();
  await expect(page.getByRole("button", { name: "Rebuild profile" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Sync GitHub" })).toBeDisabled();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("button", { name: "Save changes" })).toHaveCount(0);
  expect(config.githubRepoBranches).toEqual({ "octocat/portfolio": "feature/dossier" });
  await expect(page.getByRole("button", { name: "Rebuild profile" })).toBeEnabled();
  await page.reload();
  await page.getByRole("button", { name: "Choose repository branches" }).click();
  await expect(page.getByRole("combobox", { name: "Branch for octocat/portfolio" })).toContainText("feature/dossier");
  await page.getByRole("combobox", { name: "Branch for octocat/portfolio" }).focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("listbox")).toBeVisible();
  await expect(page.locator('[data-slot="select-content"]')).toHaveCSS("animation-name", "none");
  await page.keyboard.press("Escape");
});

test("build and sync wait for source uploads to finish", async ({ page }) => {
  let finishUpload!: () => void;
  const uploadGate = new Promise<void>((resolve) => { finishUpload = resolve; });
  await page.route("**/api/profile/sources", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await uploadGate;
    await route.fulfill({ status: 201, json: { id: "uploaded", filename: "notes.txt" } });
  });
  await page.goto("/profile");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Add source", exact: true }).click();
  await (await chooser).setFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("evidence") });
  try {
    await expect(page.getByRole("button", { name: "Rebuild profile" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Sync GitHub" })).toBeDisabled();
  } finally {
    finishUpload();
  }
  await expect(page.getByRole("button", { name: "Rebuild profile" })).toBeEnabled();
});

test("source and branch controls reflow with long names in both themes", async ({ page }, testInfo) => {
  const branchName = "feature/" + "long-project-dossier-".repeat(6);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/profile/github/repositories", (route) => route.fulfill({ json: [
    { owner: "octocat", name: "portfolio", fullName: "octocat/portfolio", defaultBranch: "main", included: true },
  ] }));
  await page.route("**/api/profile/github/repositories/octocat/portfolio/branches", (route) => route.fulfill({ json: ["main", branchName] }));
  await page.goto("/profile");
  await page.getByRole("button", { name: "Choose repository branches" }).click();
  await page.getByRole("combobox", { name: "Branch for octocat/portfolio" }).click();
  await page.getByRole("option", { name: branchName, exact: true }).click();
  await expect(page.getByRole("listbox")).toHaveCount(0);
  for (const theme of ["light", "dark"]) {
    await page.evaluate((value) => { document.documentElement.classList.remove("light", "dark"); document.documentElement.classList.add(value); }, theme);
    for (const size of [{ width: 375, height: 812 }, { width: 812, height: 375 }]) {
      await page.setViewportSize(size);
      const layout = await page.evaluate(() => ({ viewport: window.innerWidth, width: document.documentElement.scrollWidth }));
      expect(layout.width).toBeLessThanOrEqual(layout.viewport);
      await page.getByRole("combobox", { name: "Branch for octocat/portfolio" }).click();
      await expect(page.getByRole("listbox")).toBeVisible();
      const openWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(openWidth).toBeLessThanOrEqual(size.width);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("listbox")).toHaveCount(0);
    }
    await page.setViewportSize({ width: 1280, height: 1000 });
    const repositoryBounds = await page.getByRole("region", { name: "GitHub projects" }).getByText("octocat/portfolio", { exact: true }).boundingBox();
    expect(repositoryBounds!.height).toBeLessThan(60);
    const branchTrigger = page.getByRole("combobox", { name: "Branch for octocat/portfolio" });
    const textBounds = await branchTrigger.locator('[data-slot="select-value"]').boundingBox();
    const triggerBounds = await branchTrigger.boundingBox();
    expect(textBounds!.y).toBeGreaterThanOrEqual(triggerBounds!.y);
    expect(textBounds!.y + textBounds!.height).toBeLessThanOrEqual(triggerBounds!.y + triggerBounds!.height);
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await page.screenshot({ path: testInfo.outputPath(`profile-${theme}.png`), fullPage: true });
  }
});

test("profile controls remain usable with enlarged text in English and Chinese", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/profile/sources/github-exclusions", (route) => route.fulfill({ json: ["removed.md"] }));
  for (const language of ["en", "zh-CN"]) {
    await page.goto("/profile");
    await page.evaluate((value) => localStorage.setItem("resume-tailor-harness-language", value), language);
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("lang", language);
    await expect(page.getByRole("article", { name: "resume.pdf", exact: true })).toBeVisible();
    await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
    for (const width of [320, 768, 1280, 1920]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect(page.getByRole("article", { name: "resume.pdf", exact: true })).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`profile-${language}-${width}-large-text.png`), fullPage: true });
      const layout = await page.evaluate(() => ({
        width: document.documentElement.scrollWidth,
        overflow: [...document.querySelectorAll("#main-content *, .app-chrome")].filter((node) => node.getBoundingClientRect().right > innerWidth + 1).slice(0, 15).map((node) => ({ tag: node.tagName, className: node.className, text: node.textContent?.slice(0, 60) })),
      }));
      expect(layout.width, JSON.stringify(layout.overflow)).toBeLessThanOrEqual(width);
      const toolbar = page.getByRole("group", { name: language === "en" ? "Job discovery actions" : "职位发现操作" });
      const actions = await toolbar.boundingBox();
      const notifications = await page.locator(".app-chrome").locator("button").filter({ has: page.locator("svg.lucide-bell") }).boundingBox();
      expect(actions).not.toBeNull();
      expect(notifications).not.toBeNull();
      expect(actions!.y).toBeGreaterThanOrEqual(notifications!.y + notifications!.height);
    }
    await page.screenshot({ path: testInfo.outputPath(`profile-${language}-large-text.png`), fullPage: true });
  }
});
