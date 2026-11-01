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
  await page.route("**/api/notifications", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/setup/status", (route) =>
    route.fulfill({ json: setupStatus }),
  );
  await mockEmptyRuns(page);
  await page.route("**/api/run-completions?*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/profile/sources/github-exclusions", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/profile/skeleton", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/profile/suppressed-skills", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/profile/coach/sessions", (route) =>
    route.fulfill({ json: [] }),
  );
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
    }),
  );
  await page.route("**/api/profile/matrix", (route) =>
    route.fulfill({
      json: {
        generatedAt: "2026-07-10T00:00:00Z",
        groups: [
          {
            slug: "languages",
            label: "Programming Languages",
            category: "technical",
          },
          { slug: "other", label: "Other", category: "other" },
        ],
        categories: [
          { slug: "technical", label: "Technical skills" },
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
            ? [
                {
                  key: addedSkill.toLowerCase(),
                  display: addedSkill,
                  category: "hard",
                  group: "languages",
                  groupSource: "correction",
                  inferred: false,
                  strength: 0,
                  lastUsed: null,
                },
              ]
            : []),
        ],
      },
    }),
  );
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
  await page.route("**/api/profile/skills/*", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    const payload = route.request().postDataJSON();
    pythonGroup = payload.group || "languages";
    pythonGroupSource = payload.group ? "correction" : "taxonomy";
    await route.fulfill({ status: 204 });
  });
  await page.route("**/api/profile/skills/cleanup", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        beforeCount: 2,
        afterCount: 2,
        merges: [],
        pruned: [],
      },
    }),
  );
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
    }),
  );
});

test("profile depth controls and grouped skills form one working story", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/profile");
  await expect(
    page.getByRole("heading", { name: "Profile", exact: true }),
  ).toBeVisible();
  // Documents is the default tab — sources + repo controls live here.
  await expect(
    page.getByRole("article", { name: /github--portfolio\.md/i }),
  ).toContainText("GitHub");
  await expect(page.getByLabel("mode for github--portfolio.md")).toHaveCount(0);

  await page.getByRole("button", { name: "Add note" }).click();
  await page.getByLabel("Note title").fill("On-call");
  await page.getByLabel("Note text").fill("Led the rotation.");
  const noteRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/profile/sources/note") &&
      request.method() === "POST",
  );
  await page.getByRole("button", { name: "Save note" }).click();
  expect((await noteRequest).postDataJSON()).toEqual({
    title: "On-call",
    text: "Led the rotation.",
  });
  await expect(page.getByRole("dialog", { name: "Add a note" })).toHaveCount(0);

  await page.getByText("Import preferences", { exact: true }).click();
  await page
    .getByLabel("Always include repositories")
    .fill("portfolio, flagship");
  await page.getByLabel("Exclude repositories").fill("archive");
  await page.getByLabel("Repository limit").fill("5");
  const saveRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/config/profile") &&
      request.method() === "PUT",
  );
  await page.getByRole("button", { name: "Save changes" }).click();
  expect((await saveRequest).postDataJSON()).toMatchObject({
    githubRepoAllow: ["portfolio", "flagship"],
    githubRepoDeny: ["archive"],
    githubRepoLimit: 5,
  });
  await expect(page.getByRole("button", { name: "Save changes" })).toHaveCount(
    0,
  );

  // Skills are behind their own tab now, no longer stacked under Documents.
  await page.getByRole("tab", { name: "Skills" }).click();
  await expect(
    page.getByRole("heading", { name: "Your skill library" }),
  ).toBeVisible();
  await expect(page.getByText("Python", { exact: true })).toBeVisible();
  await expect(page.getByText("vFlash", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Add skill", exact: true }).click();
  const addDialog = page.getByRole("dialog", { name: "Add a skill" });
  await addDialog.getByLabel("Skill name").fill("TypeScript");
  await addDialog
    .getByLabel("Group", { exact: true })
    .selectOption("languages");
  const addRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/profile/skills") &&
      request.method() === "POST",
  );
  await addDialog
    .getByRole("button", { name: "Add skill", exact: true })
    .click();
  expect((await addRequest).postDataJSON()).toEqual({
    name: "TypeScript",
    category: "hard",
    aliases: [],
    group: "languages",
  });
  await expect(addDialog).toHaveCount(0);

  for (const group of ["other", ""]) {
    await page.getByRole("button", { name: "Edit Python" }).click();
    const dialog = page.getByRole("dialog", { name: "Edit skill" });
    await dialog.getByLabel("Group", { exact: true }).selectOption(group);
    const editRequest = page.waitForRequest(
      (request) =>
        request.url().endsWith("/api/profile/skills/python") &&
        request.method() === "PUT",
    );
    await dialog.getByRole("button", { name: "Save changes" }).click();
    expect((await editRequest).postDataJSON()).toMatchObject({
      name: "Python",
      group,
    });
    await expect(dialog).toHaveCount(0);
  }
  expect(consoleErrors).toEqual([]);
});

test("profile settings stay contained at a narrow viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/profile");
  await page.getByRole("tab", { name: "Skills" }).click();
  await expect(
    page.getByRole("heading", { name: "Your skill library" }),
  ).toBeVisible();

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

test("source files can be replaced and removed without losing their roles", async ({
  page,
}) => {
  let rows = [
    {
      id: "resume",
      filename: "resume.pdf",
      mode: "literal",
      primary: true,
      origin: "upload",
      anchor: null,
      addedAt: "2026-07-10",
      fragmentStatus: "cached",
      fileExists: true,
    },
    {
      id: "github-repo",
      filename: "github--portfolio.md",
      mode: "project",
      primary: false,
      origin: "github",
      anchor: null,
      addedAt: "2026-07-10",
      fragmentStatus: "missing",
      fileExists: true,
    },
  ];
  let excluded: string[] = [];
  await page.route("**/api/profile/sources", (route) =>
    route.fulfill({ json: rows }),
  );
  await page.route(
    "**/api/profile/sources/github-exclusions",
    async (route) => {
      if (route.request().method() === "DELETE") {
        excluded = [];
        await route.fulfill({ status: 204 });
      } else await route.fulfill({ json: excluded });
    },
  );
  await page.route("**/api/profile/sources/*/file", async (route) => {
    const id = route.request().url().split("/").at(-2);
    const body = route.request().postData() ?? "";
    expect(body).not.toContain('name="primary"');
    expect(body).not.toContain('name="mode"');
    rows = rows.map((row) =>
      row.id === id
        ? {
            ...row,
            filename: id === "resume" ? "new-resume.pdf" : "updated-dossier.md",
            origin: "upload",
            fragmentStatus: "missing",
          }
        : row,
    );
    await route.fulfill({ json: rows.find((row) => row.id === id) });
  });
  await page.route(
    /\/api\/profile\/sources\/github-repo\?purge=true$/,
    async (route) => {
      rows = rows.filter((row) => row.id !== "github-repo");
      excluded = ["updated-dossier.md"];
      await route.fulfill({ status: 204 });
    },
  );

  await page.goto("/profile");
  const githubRow = page.getByRole("article", {
    name: /github--portfolio\.md/i,
  });
  await expect(githubRow).toContainText("Needs build");
  await expect(githubRow).not.toContainText("File missing");
  const chooser = page.waitForEvent("filechooser");
  await page
    .getByRole("button", { name: "Replace github--portfolio.md" })
    .click();
  await (
    await chooser
  ).setFiles({
    name: "updated-dossier.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Updated evidence"),
  });
  await expect(
    page.getByRole("article", { name: /updated-dossier\.md/i }),
  ).toContainText("Project");
  await expect(
    page.getByRole("article", { name: /resume\.pdf/i }),
  ).toContainText("Primary");

  const resumeChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Replace resume.pdf" }).click();
  await (
    await resumeChooser
  ).setFiles({
    name: "new-resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("new resume"),
  });
  await expect(
    page.getByRole("article", { name: /new-resume\.pdf/i }),
  ).toContainText("Primary");
  await page.getByRole("button", { name: "Remove updated-dossier.md" }).click();
  await page
    .getByRole("button", { name: "Remove source", exact: true })
    .click();
  await expect(
    page.getByRole("article", { name: /updated-dossier\.md/i }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Restore removed GitHub sources" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("article", { name: /updated-dossier\.md/i }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Restore removed GitHub sources" })
    .click();
  await expect(
    page.getByRole("button", { name: "Restore removed GitHub sources" }),
  ).toHaveCount(0);
});

test("repository branch choices are saved and survive reload", async ({
  page,
}) => {
  let config = {
    githubUsername: "octocat",
    githubRepoAllow: [],
    githubRepoDeny: [],
    githubRepoLimit: 20,
    githubRepoBranches: {} as Record<string, string>,
  };
  await page.route("**/api/config/profile", async (route) => {
    if (route.request().method() === "PUT")
      config = route.request().postDataJSON();
    await route.fulfill({ json: config });
  });
  await page.route("**/api/profile/github/repositories", (route) =>
    route.fulfill({
      json: [
        {
          owner: "octocat",
          name: "portfolio",
          fullName: "octocat/portfolio",
          defaultBranch: "main",
          included: true,
          selectedBranch:
            config.githubRepoBranches["octocat/portfolio"] ?? null,
        },
      ],
    }),
  );
  await page.route(
    "**/api/profile/github/repositories/octocat/portfolio/branches",
    (route) => route.fulfill({ json: ["main", "dev", "feature/dossier"] }),
  );

  await page.goto("/profile");
  await page
    .getByRole("button", { name: "Choose repository branches" })
    .click();
  const branch = page.getByRole("combobox", {
    name: "Branch for octocat/portfolio",
  });
  await branch.click();
  await page
    .getByRole("option", { name: "feature/dossier", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Rebuild profile" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Sync GitHub" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("button", { name: "Save changes" })).toHaveCount(
    0,
  );
  expect(config.githubRepoBranches).toEqual({
    "octocat/portfolio": "feature/dossier",
  });
  await expect(
    page.getByRole("button", { name: "Rebuild profile" }),
  ).toBeEnabled();
  await page.reload();
  await page
    .getByRole("button", { name: "Choose repository branches" })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Branch for octocat/portfolio" }),
  ).toContainText("feature/dossier");
  await page
    .getByRole("combobox", { name: "Branch for octocat/portfolio" })
    .focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("listbox")).toBeVisible();
  await expect(page.locator('[data-slot="select-content"]')).toHaveCSS(
    "animation-name",
    "none",
  );
  await page.keyboard.press("Escape");
});

test("build and sync wait for source uploads to finish", async ({ page }) => {
  let finishUpload!: () => void;
  const uploadGate = new Promise<void>((resolve) => {
    finishUpload = resolve;
  });
  await page.route("**/api/profile/sources", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await uploadGate;
    await route.fulfill({
      status: 201,
      json: { id: "uploaded", filename: "notes.txt" },
    });
  });
  await page.goto("/profile");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Add source", exact: true }).click();
  await (
    await chooser
  ).setFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("evidence"),
  });
  try {
    await expect(
      page.getByRole("button", { name: "Rebuild profile" }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "Sync GitHub" }),
    ).toBeDisabled();
  } finally {
    finishUpload();
  }
  await expect(
    page.getByRole("button", { name: "Rebuild profile" }),
  ).toBeEnabled();
});

test("source and branch controls reflow with long names in both themes", async ({
  page,
}, testInfo) => {
  const branchName = "feature/" + "long-project-dossier-".repeat(6);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/profile/github/repositories", (route) =>
    route.fulfill({
      json: [
        {
          owner: "octocat",
          name: "portfolio",
          fullName: "octocat/portfolio",
          defaultBranch: "main",
          included: true,
        },
      ],
    }),
  );
  await page.route(
    "**/api/profile/github/repositories/octocat/portfolio/branches",
    (route) => route.fulfill({ json: ["main", branchName] }),
  );
  await page.goto("/profile");
  await page
    .getByRole("button", { name: "Choose repository branches" })
    .click();
  await page
    .getByRole("combobox", { name: "Branch for octocat/portfolio" })
    .click();
  await page.getByRole("option", { name: branchName, exact: true }).click();
  await expect(page.getByRole("listbox")).toHaveCount(0);
  for (const theme of ["light", "dark"]) {
    await page.evaluate((value) => {
      document.documentElement.classList.remove("light", "dark");
      document.documentElement.classList.add(value);
    }, theme);
    for (const size of [
      { width: 375, height: 812 },
      { width: 812, height: 375 },
    ]) {
      await page.setViewportSize(size);
      const layout = await page.evaluate(() => ({
        viewport: window.innerWidth,
        width: document.documentElement.scrollWidth,
      }));
      expect(layout.width).toBeLessThanOrEqual(layout.viewport);
      await page
        .getByRole("combobox", { name: "Branch for octocat/portfolio" })
        .click();
      await expect(page.getByRole("listbox")).toBeVisible();
      const openWidth = await page.evaluate(
        () => document.documentElement.scrollWidth,
      );
      expect(openWidth).toBeLessThanOrEqual(size.width);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("listbox")).toHaveCount(0);
    }
    await page.setViewportSize({ width: 1280, height: 1000 });
    const repositoryBounds = await page
      .getByRole("region", { name: "GitHub projects" })
      .getByText("octocat/portfolio", { exact: true })
      .boundingBox();
    expect(repositoryBounds!.height).toBeLessThan(60);
    const branchTrigger = page.getByRole("combobox", {
      name: "Branch for octocat/portfolio",
    });
    const textBounds = await branchTrigger
      .locator('[data-slot="select-value"]')
      .boundingBox();
    const triggerBounds = await branchTrigger.boundingBox();
    expect(textBounds!.y).toBeGreaterThanOrEqual(triggerBounds!.y);
    expect(textBounds!.y + textBounds!.height).toBeLessThanOrEqual(
      triggerBounds!.y + triggerBounds!.height,
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await page.screenshot({
      path: testInfo.outputPath(`profile-${theme}.png`),
      fullPage: true,
    });
  }
});

test("profile controls remain usable with enlarged text in English and Chinese", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/profile/sources/github-exclusions", (route) =>
    route.fulfill({ json: ["removed.md"] }),
  );
  for (const language of ["en", "zh-CN"]) {
    await page.goto("/profile");
    await page.evaluate(
      (value) => localStorage.setItem("resume-tailor-harness-language", value),
      language,
    );
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("lang", language);
    const resume = page.getByRole("article", {
      name: "resume.pdf",
      exact: true,
    });
    await expect(resume).toBeVisible();
    await expect(resume).toContainText(language === "en" ? "Ready" : "已就绪");
    await expect(
      page.getByText(
        language === "en"
          ? "Choose GitHub branches (optional)"
          : "选择 GitHub 分支（可选）",
        { exact: true },
      ),
    ).toBeVisible();
    await page.evaluate(() => {
      document.documentElement.style.fontSize = "200%";
    });
    for (const width of [320, 768, 1280, 1920]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect(
        page.getByRole("article", { name: "resume.pdf", exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(
          `profile-${language}-${width}-large-text.png`,
        ),
        fullPage: true,
      });
      const layout = await page.evaluate(() => ({
        width: document.documentElement.scrollWidth,
        overflow: [...document.querySelectorAll("#main-content *, .app-chrome")]
          .filter((node) => node.getBoundingClientRect().right > innerWidth + 1)
          .slice(0, 15)
          .map((node) => ({
            tag: node.tagName,
            className: node.className,
            text: node.textContent?.slice(0, 60),
          })),
      }));
      expect(layout.width, JSON.stringify(layout.overflow)).toBeLessThanOrEqual(
        width,
      );
      const toolbar = page.getByRole("group", {
        name: language === "en" ? "Job discovery actions" : "职位发现操作",
      });
      const actions = await toolbar.boundingBox();
      const notifications = await page
        .locator(".app-chrome")
        .locator("button")
        .filter({ has: page.locator("svg.lucide-bell") })
        .boundingBox();
      expect(actions).not.toBeNull();
      expect(notifications).not.toBeNull();
      expect(actions!.y).toBeGreaterThanOrEqual(
        notifications!.y + notifications!.height,
      );
    }
    await page.screenshot({
      path: testInfo.outputPath(`profile-${language}-large-text.png`),
      fullPage: true,
    });
  }
});

test("skill library reflows in both languages, themes, and enlarged text", async ({
  page,
}, testInfo) => {
  const skillNames = [
    "Python",
    "TypeScript",
    "PostgreSQL",
    "Kubernetes",
    "React",
    "FastAPI",
    "Data pipelines",
    "API design",
    "Test automation",
    "Observability",
    "Docker",
    "Distributed systems",
  ];
  await page.route("**/api/profile/matrix", (route) =>
    route.fulfill({
      json: {
        generatedAt: "2026-11-01T10:00:00Z",
        categories: [
          { slug: "technical", label: "Technical skills" },
          { slug: "people", label: "People & delivery" },
          { slug: "other", label: "Other" },
        ],
        groups: [
          {
            slug: "languages",
            label: "Programming Languages",
            category: "technical",
          },
          {
            slug: "backend-apis",
            label: "Backend & APIs",
            category: "technical",
          },
          { slug: "other", label: "Other", category: "other" },
        ],
        rows: skillNames.map((display, i) => ({
          key: display.toLowerCase(),
          display,
          aliases: i === 0 ? ["Python 3", "CPython"] : [],
          category: "hard",
          group: i < 2 ? "languages" : "backend-apis",
          inferred: i > 6,
          groupSource: i === 1 ? "correction" : "taxonomy",
          strength: 4,
          evidenceFactIds: ["work"],
        })),
      },
    }),
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const language of ["en", "zh-CN"]) {
    await page.addInitScript(
      (value) => localStorage.setItem("resume-tailor-harness-language", value),
      language,
    );
    for (const theme of ["light", "dark"]) {
      for (const width of [1280, 320]) {
        await page.setViewportSize({ width, height: 900 });
        await page.goto("/profile?tab=skills");
        const heading = page.getByRole("heading", {
          name: language === "en" ? "Your skill library" : "个人技能库",
        });
        await expect(heading).toBeVisible();
        await page.evaluate(
          (value) =>
            document.documentElement.classList.toggle("dark", value === "dark"),
          theme,
        );
        const layout = await page.evaluate(() => ({
          viewport: innerWidth,
          document: document.documentElement.scrollWidth,
        }));
        expect(layout.document).toBeLessThanOrEqual(layout.viewport);
        await heading.evaluate((node) => {
          node.scrollIntoView({ block: "start" });
          const chrome = document.querySelector(".app-chrome");
          scrollBy(0, -(chrome?.getBoundingClientRect().bottom ?? 160) - 16);
        });
        await page.screenshot({
          path: testInfo.outputPath(`skills-${language}-${theme}-${width}.png`),
        });
      }
    }
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.evaluate(() => (document.documentElement.style.fontSize = "200%"));
  const enlargedLayout = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    overflow: [...document.querySelectorAll("#main-content *")]
      .filter((node) => node.getBoundingClientRect().right > innerWidth + 1)
      .slice(0, 12)
      .map((node) => ({
        tag: node.tagName,
        className: node.className,
        text: node.textContent?.slice(0, 70),
      })),
  }));
  expect(
    enlargedLayout.width,
    JSON.stringify(enlargedLayout.overflow),
  ).toBeLessThanOrEqual(1280);
  const skillNamesAtLargeText = page.locator(
    'section[aria-labelledby="skill-library-heading"] li > div.min-w-0',
  );
  const firstSkillWidth = await skillNamesAtLargeText
    .first()
    .evaluate((node) => node.getBoundingClientRect().width);
  expect(firstSkillWidth).toBeGreaterThan(200);
  await page.screenshot({
    path: testInfo.outputPath("skills-zh-enlarged.png"),
    fullPage: true,
    animations: "disabled",
  });
});

test("skill editor and organization controls support keyboard and narrow screens", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/profile?tab=skills");
  const add = page.getByRole("button", { name: "Add skill", exact: true });
  await add.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Add a skill" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS("transition-property", "none");
  await expect(page.locator('[data-slot="dialog-overlay"]')).toHaveCSS(
    "transition-property",
    "none",
  );
  await page.getByLabel("Skill name").fill("TypeScript");
  await page.getByLabel("Aliases", { exact: true }).fill("TS");
  await expect(dialog).toHaveJSProperty(
    "scrollWidth",
    await dialog.evaluate((node) => node.clientWidth),
  );
  await page.screenshot({
    path: testInfo.outputPath("skill-editor-mobile.png"),
  });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(add).toBeFocused();
  await page
    .getByRole("button", { name: "Groups & categories", exact: true })
    .click();
  const organization = page.getByRole("dialog", {
    name: "Groups & categories",
  });
  await expect(organization).toBeVisible();
  await page.getByRole("button", { name: "Add group", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("My engineering tools");
  await page.screenshot({
    path: testInfo.outputPath("skill-organization-mobile.png"),
  });
  const bounds = await organization.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(375);
});

async function mockCompactSkills(
  page: import("@playwright/test").Page,
  extraSkills = 0,
) {
  let categories = [
    { slug: "technical", label: "Technical skills", customized: false },
    { slug: "people", label: "People & delivery", customized: false },
    { slug: "other", label: "Other", customized: false },
  ];
  let groups = [
    {
      slug: "languages",
      label: "Programming Languages",
      category: "technical",
      customized: false,
    },
    {
      slug: "backend-apis",
      label: "Backend & APIs",
      category: "technical",
      customized: false,
    },
    {
      slug: "leadership-management",
      label: "Leadership & Management",
      category: "people",
      customized: false,
    },
    { slug: "other", label: "Other", category: "other", customized: false },
  ];
  let rows = [
    {
      key: "python",
      display: "Python",
      aliases: ["py", "Python 3"],
      category: "hard",
      group: "languages" as string | null,
      groupSource: "taxonomy",
      inferred: false,
      strength: 3,
    },
    {
      key: "leadership",
      display: "Team leadership",
      aliases: [],
      category: "soft",
      group: "leadership-management",
      groupSource: "taxonomy",
      inferred: true,
      strength: 2,
    },
    ...Array.from({ length: extraSkills }, (_, index) => ({
      key: `skill ${index}`,
      display: `Skill ${index}`,
      aliases: [],
      category: "hard",
      group: "backend-apis",
      groupSource: "taxonomy",
      inferred: false,
      strength: 1,
    })),
  ];
  const moves: Array<{ key: string; group: string }> = [];
  const edits: Array<{ kind: string; method: string; body: unknown }> = [];
  let failMove = false;
  let sequence = 1;
  await page.route("**/api/profile/skills", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON();
    rows.push({
      key: body.name.toLowerCase(),
      display: body.name,
      aliases: body.aliases,
      category: body.category,
      group: body.group || "other",
      groupSource: "correction",
      inferred: false,
      strength: 0,
    });
    await route.fulfill({
      status: 201,
      json: {
        id: "manual-skill",
        kind: "new_skill",
        name: body.name,
        category: body.category,
        addedAt: "2026-11-01T10:00:00Z",
      },
    });
  });
  await page.route("**/api/profile/matrix", (route) =>
    route.fulfill({
      json: { generatedAt: "2026-11-01T10:00:00Z", categories, groups, rows },
    }),
  );
  await page.route("**/api/profile/skills/*/group", async (route) => {
    const request = route.request();
    const key = decodeURIComponent(
      new URL(request.url()).pathname.split("/").at(-2)!,
    );
    if (failMove) {
      failMove = false;
      await route.fulfill({
        status: 422,
        json: {
          error: {
            code: "VALIDATION_ERROR",
            message: "Move failed. Try again.",
          },
        },
      });
      return;
    }
    const group =
      request.method() === "DELETE"
        ? "languages"
        : request.postDataJSON().group;
    moves.push({ key, group });
    rows = rows.map((row) =>
      row.key === key
        ? {
            ...row,
            group,
            groupSource:
              request.method() === "DELETE" ? "taxonomy" : "correction",
          }
        : row,
    );
    await route.fulfill({ status: 204 });
  });
  await page.route(
    /\/api\/profile\/skill-(groups|categories)(?:\/[^/?]+)?$/,
    async (route) => {
      const request = route.request();
      const parts = new URL(request.url()).pathname.split("/");
      const kind = parts[3] === "skill-groups" ? "group" : "category";
      const key = parts[4];
      const method = request.method();
      const body = method === "DELETE" ? {} : request.postDataJSON();
      edits.push({ kind, method, body });
      if (method === "POST") {
        const slug = `custom-${String(sequence++).padStart(12, "0")}`;
        if (kind === "group")
          groups.push({
            slug,
            label: body.label,
            category: body.category,
            customized: true,
          });
        else categories.push({ slug, label: body.label, customized: true });
      } else if (method === "PUT") {
        if (kind === "group")
          groups = groups.map((item) =>
            item.slug === key
              ? {
                  ...item,
                  label: body.label,
                  category: body.category,
                  customized: true,
                }
              : item,
          );
        else
          categories = categories.map((item) =>
            item.slug === key
              ? { ...item, label: body.label, customized: true }
              : item,
          );
      } else if (method === "DELETE") {
        if (kind === "group") {
          groups = groups.filter((item) => item.slug !== key);
          rows = rows.map((row) =>
            row.group === key ? { ...row, group: null } : row,
          );
        } else {
          categories = categories.filter((item) => item.slug !== key);
          groups = groups.map((item) =>
            item.category === key ? { ...item, category: "other" } : item,
          );
        }
      }
      await route.fulfill(
        method === "POST"
          ? { status: 201, json: { ok: true } }
          : { status: 204 },
      );
    },
  );
  await page.route("**/api/profile/skills/*", async (route) => {
    const request = route.request();
    if (!["PUT", "DELETE"].includes(request.method())) return route.fallback();
    const key = decodeURIComponent(
      new URL(request.url()).pathname.split("/").at(-1)!,
    );
    if (request.method() === "DELETE")
      rows = rows.filter((row) => row.key !== key);
    else {
      const body = request.postDataJSON();
      rows = rows.map((row) =>
        row.key === key
          ? {
              ...row,
              display: body.name,
              aliases: body.aliases,
              category: body.category,
              group: body.group || row.group,
            }
          : row,
      );
    }
    await route.fulfill({ status: 204 });
  });
  return {
    moves,
    edits,
    failNextMove: () => {
      failMove = true;
    },
  };
}

test("compact view displays every skill and remembers its density", async ({
  page,
}) => {
  await mockCompactSkills(page, 48);
  await page.goto("/profile?tab=skills");
  await page.getByRole("button", { name: "Compact", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Skill 47", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Next skills page" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Group actions for Other" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Compact", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Detailed", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Next skills page" }),
  ).toBeVisible();
});

test("skill context windows support keyboard moving, editing and deleting", async ({
  page,
}) => {
  const state = await mockCompactSkills(page);
  await page.goto("/profile?tab=skills");
  await page.getByRole("button", { name: "Compact", exact: true }).click();
  const python = page.getByRole("button", { name: "Python", exact: true });
  await python.focus();
  await page.keyboard.press("Enter");
  let popup = page.getByRole("dialog", { name: "Python", exact: true });
  await expect(popup).toBeVisible();
  await expect(popup).toHaveCSS("animation-name", "none");
  await popup.getByLabel("Move to group").selectOption("leadership-management");
  await popup.getByRole("button", { name: "Move skill", exact: true }).click();
  await expect
    .poll(() => state.moves)
    .toEqual([{ key: "python", group: "leadership-management" }]);
  await expect(
    page.locator(
      '[data-skill-drop-group="leadership-management"] [data-skill-chip="python"]',
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Python", exact: true }).click();
  popup = page.getByRole("dialog", { name: "Python", exact: true });
  await popup.getByRole("button", { name: "Edit skill", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "Edit skill", exact: true });
  await expect(editor.getByLabel("Skill name")).toBeFocused();
  await editor.getByLabel("Skill name").fill("Python programming");
  await editor
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Python programming", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Python programming", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Python programming", exact: true })
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Python programming", exact: true }),
  ).toHaveCount(0);
});

test("group contexts add a skill with keyboard focus and keep its chosen group", async ({
  page,
}) => {
  await mockCompactSkills(page);
  await page.goto("/profile?tab=skills");
  await page.getByRole("button", { name: "Compact", exact: true }).click();
  const trigger = page.getByRole("button", {
    name: "Group actions for Programming Languages",
    exact: true,
  });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await page
    .getByRole("dialog", { name: "Programming Languages", exact: true })
    .getByRole("button", { name: "Add skill", exact: true })
    .click();
  const editor = page.getByRole("dialog", { name: "Add a skill", exact: true });
  await expect(editor.getByLabel("Skill name")).toBeFocused();
  await expect(editor.getByLabel("Group", { exact: true })).toHaveValue(
    "languages",
  );
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await trigger.click();
  await page
    .getByRole("dialog", { name: "Programming Languages", exact: true })
    .getByRole("button", { name: "Add skill", exact: true })
    .click();
  await editor.getByLabel("Skill name").fill("TypeScript");
  await editor.getByRole("button", { name: "Add skill", exact: true }).click();
  await expect(
    page.locator(
      '[data-skill-drop-group="languages"] [data-skill-chip="typescript"]',
    ),
  ).toBeVisible();
  await expect(trigger).toBeFocused();
  await page
    .getByRole("button", { name: "Add skill: Other", exact: true })
    .click();
  await expect(editor.getByLabel("Group", { exact: true })).toHaveValue(
    "other",
  );
  await editor.getByLabel("Skill name").fill("Documentation");
  await editor.getByRole("button", { name: "Add skill", exact: true }).click();
  await expect(
    page.locator(
      '[data-skill-drop-group="other"] [data-skill-chip="documentation"]',
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Group actions for Other", exact: true }),
  ).toBeFocused();
});

test("pointer dragging moves skills, cancels safely, and reports a rejected move", async ({
  page,
}) => {
  const state = await mockCompactSkills(page);
  await page.setViewportSize({ width: 1440, height: 1400 });
  await page.goto("/profile?tab=skills");
  await page.getByRole("button", { name: "Compact", exact: true }).click();
  const source = page.locator('[data-drag-skill="python"]');
  const destination = page.locator(
    '[data-skill-drop-group="leadership-management"]',
  );
  await source.scrollIntoViewIfNeeded();
  let from = (await source.boundingBox())!;
  let to = (await destination.boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, {
    steps: 12,
  });
  await page.keyboard.press("Escape");
  await page.mouse.up();
  expect(state.moves).toEqual([]);
  await expect(
    page.locator(
      '[data-skill-drop-group="languages"] [data-skill-chip="python"]',
    ),
  ).toBeVisible();
  from = (await source.boundingBox())!;
  to = (await destination.boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, {
    steps: 12,
  });
  await page.mouse.up();
  await expect
    .poll(() => state.moves)
    .toEqual([{ key: "python", group: "leadership-management" }]);
  await expect(destination.locator('[data-skill-chip="python"]')).toBeVisible();
  state.failNextMove();
  await page.getByRole("button", { name: "Python", exact: true }).click();
  const popup = page.getByRole("dialog", { name: "Python", exact: true });
  await popup.getByLabel("Move to group").selectOption("other");
  await popup.getByRole("button", { name: "Move skill", exact: true }).click();
  await expect(popup.getByRole("alert")).toContainText("Move failed");
  await expect(destination.locator('[data-skill-chip="python"]')).toBeVisible();
});

test("category and group context windows create, rename and delete containers", async ({
  page,
}) => {
  const state = await mockCompactSkills(page);
  await page.goto("/profile?tab=skills");
  await page.getByRole("button", { name: "Compact", exact: true }).click();
  await page.getByRole("button", { name: "Add category", exact: true }).click();
  const popup = page.getByRole("dialog");
  await popup.getByLabel("Name", { exact: true }).fill("Specialty");
  await popup
    .getByRole("button", { name: "Add category", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Category actions for Specialty",
      exact: true,
    })
    .click();
  await popup.getByRole("button", { name: "Add group", exact: true }).click();
  await popup.getByLabel("Name", { exact: true }).fill("My tools");
  await popup.getByRole("button", { name: "Add group", exact: true }).click();
  await page
    .getByRole("button", { name: "Group actions for My tools", exact: true })
    .click();
  await popup.getByRole("button", { name: "Edit group", exact: true }).click();
  await popup.getByLabel("Name", { exact: true }).fill("Core tools");
  await popup
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Group actions for Core tools",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Category actions for Specialty",
      exact: true,
    })
    .click();
  await popup
    .getByRole("button", { name: "Edit category", exact: true })
    .click();
  await popup.getByLabel("Name", { exact: true }).fill("Personal specialty");
  await popup
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Filter by group", exact: true })
    .selectOption("custom-000000000002");
  await page
    .getByRole("button", { name: "Group actions for Core tools", exact: true })
    .click();
  await popup
    .getByRole("button", { name: "Delete group", exact: true })
    .click();
  await popup.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Group actions for Core tools",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Filter by group", exact: true }),
  ).toHaveValue("all");
  await page
    .getByRole("combobox", { name: "Skill categories", exact: true })
    .selectOption("custom-000000000001");
  await page
    .getByRole("button", {
      name: "Category actions for Personal specialty",
      exact: true,
    })
    .click();
  await popup
    .getByRole("button", { name: "Delete category", exact: true })
    .click();
  await popup.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Category actions for Personal specialty",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Skill categories", exact: true }),
  ).toHaveValue("all");
  expect(state.edits.map((edit) => edit.method)).toEqual([
    "POST",
    "POST",
    "PUT",
    "PUT",
    "DELETE",
    "DELETE",
  ]);
});

test("touch dragging moves a skill and category drops ask for a destination", async ({
  page,
}) => {
  const state = await mockCompactSkills(page);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.goto("/profile?tab=skills");
  await page.getByRole("button", { name: "Compact", exact: true }).click();
  const source = page.locator('[data-drag-skill="python"]');
  await source.scrollIntoViewIfNeeded();
  const header = page
    .locator('[data-skill-drop-category="technical"] > div')
    .first();
  let from = (await source.boundingBox())!;
  let to = (await header.boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + 40, to.y + to.height / 2, { steps: 10 });
  await page.mouse.up();
  const popup = page.getByRole("dialog", {
    name: "Technical skills",
    exact: true,
  });
  await expect(popup).toBeVisible();
  await expect(popup).toContainText("Choose a group in this category");
  expect(state.moves).toEqual([]);
  await popup.getByLabel("Move to group").selectOption("backend-apis");
  await popup.getByRole("button", { name: "Move skill", exact: true }).click();
  await expect.poll(() => state.moves).toHaveLength(1);
  await expect(
    page.locator(
      '[data-skill-drop-group="backend-apis"] [data-skill-chip="python"]',
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Python", exact: true }),
  ).toBeEnabled();

  await page.setViewportSize({ width: 375, height: 1000 });
  await source.scrollIntoViewIfNeeded();
  const destination = page.locator('[data-skill-drop-group="languages"]');
  from = (await source.boundingBox())!;
  to = (await destination.boundingBox())!;
  const session = await page.context().newCDPSession(page);
  await session.send("Emulation.setTouchEmulationEnabled", { enabled: true });
  await session.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [
      { x: from.x + from.width / 2, y: from.y + from.height / 2, id: 1 },
    ],
  });
  for (let step = 1; step <= 10; step++) {
    await session.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [
        {
          x:
            from.x +
            from.width / 2 +
            ((to.x + to.width / 2 - from.x - from.width / 2) * step) / 10,
          y:
            from.y +
            from.height / 2 +
            ((to.y + to.height / 2 - from.y - from.height / 2) * step) / 10,
          id: 1,
        },
      ],
    });
  }
  await session.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  await expect
    .poll(() => state.moves)
    .toEqual([
      { key: "python", group: "backend-apis" },
      { key: "python", group: "languages" },
    ]);
  await expect(destination.locator('[data-skill-chip="python"]')).toBeVisible();
  await session.detach();
});

test("compact skills and click contexts reflow across languages, themes and text sizes", async ({
  page,
}, testInfo) => {
  test.setTimeout(60_000);
  await mockCompactSkills(page, 10);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const language of ["en", "zh-CN"]) {
    await page.addInitScript((value) => {
      localStorage.setItem("resume-tailor-harness-language", value);
      localStorage.setItem("profile-skills-view", "compact");
    }, language);
    for (const theme of ["light", "dark"]) {
      for (const width of [1280, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.goto("/profile?tab=skills");
        await expect(
          page.getByRole("button", { name: "Python", exact: true }),
        ).toBeVisible();
        await page.evaluate(
          (value) =>
            document.documentElement.classList.toggle("dark", value === "dark"),
          theme,
        );
        const board = page.locator('[data-skill-drop-category="technical"]');
        await board.scrollIntoViewIfNeeded();
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
        ).toBeLessThanOrEqual(width);
        await page.screenshot({
          path: testInfo.outputPath(
            `compact-${language}-${theme}-${width}.png`,
          ),
          fullPage: width === 1280,
        });
        await page.getByRole("button", { name: "Python", exact: true }).click();
        const popup = page.getByRole("dialog", { name: "Python", exact: true });
        await expect(popup).toBeVisible();
        await expect(popup).toHaveCSS("animation-name", "none");
        const bounds = (await popup.boundingBox())!;
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
        await expect(popup).toHaveJSProperty(
          "scrollWidth",
          await popup.evaluate((node) => node.clientWidth),
        );
        await page.screenshot({
          path: testInfo.outputPath(
            `context-${language}-${theme}-${width}.png`,
          ),
        });
        await page.keyboard.press("Escape");
        await expect(
          page.getByRole("button", { name: "Python", exact: true }),
        ).toBeFocused();
      }
    }
    await page.evaluate(
      () => (document.documentElement.style.fontSize = "200%"),
    );
    for (const width of [320, 1280]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.getByRole("button", { name: "Python", exact: true }).click();
      const popup = page.getByRole("dialog", { name: "Python", exact: true });
      await expect(popup).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      await expect(popup).toHaveJSProperty(
        "scrollWidth",
        await popup.evaluate((node) => node.clientWidth),
      );
      await page.screenshot({
        path: testInfo.outputPath(
          `compact-${language}-${width}-large-text.png`,
        ),
      });
      await page.keyboard.press("Escape");
    }
  }
});
