import { expect, test } from "@playwright/test";

import { mockEmptyRuns } from "./support";

for (const language of ["en", "zh-CN"] as const) {
  for (const width of [375, 768, 1280]) {
    test(`job skills use the personal library editor in ${language} at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((selectedLanguage) => {
        localStorage.setItem("resume-tailor-harness-language", selectedLanguage);
        localStorage.setItem("theme", selectedLanguage === "en" ? "light" : "dark");
      }, language);
      const chinese = language === "zh-CN";
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await mockEmptyRuns(page);
      await page.route("**/api/notifications", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/board-views?*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/run-completions?*", (route) => route.fulfill({ json: [] }));
      await page.route("**/api/setup/status", (route) => route.fulfill({ json: {
        secrets: { anthropicKey: true, anyLlmKey: true },
        profile: { documentCount: 1, hasResume: true, factsBuiltAt: "2026-11-01T00:00:00Z" },
        search: { configured: true }, sources: { enabledCount: 1 }, complete: true,
      } }));
      let newSkill: { name: string; aliases: string[]; category: string; group: string } | null = null;
      let aliasSaved = false;
      const skills = () => [
        { name: "Rust programming", required: true, covered: newSkill !== null },
        { name: "Python3", required: false, covered: aliasSaved },
      ];
      await page.route("**/api/shortlist*", (route) => route.fulfill({ json: {
        data: [7, 8].map((id) => ({ jobId: id, company: "Acme", title: id === 7 ? "Staff Engineer" : "Other Engineer", location: "Remote", fitScore: 88, skills: skills() })),
        pagination: { page: 1, pageSize: 200, totalItems: 2, totalPages: 1 }, facets: {}, total: 2,
      } }));
      await page.route("**/api/jobs/7", (route) => route.fulfill({ json: {
        id: 7, source: "manual", company: "Acme", title: "Staff Engineer", location: "Remote", url: "https://jobs.example.test/7", jdText: "Build platform services.", status: "shortlisted", fitScore: 88, skills: skills(), resumeVersions: [], coverLetters: [], application: null,
      } }));
      await page.route("**/api/profile/matrix", (route) => route.fulfill({ json: {
        generatedAt: "2026-11-01T00:00:00Z",
        groups: [{ slug: "languages", label: "Programming Languages", category: "technical" }],
        categories: [{ slug: "technical", label: "Technical skills" }],
        rows: [],
      } }));
      await page.route("**/api/profile/skills", async (route) => {
        if (route.request().method() === "POST") {
          newSkill = route.request().postDataJSON();
          return route.fulfill({ status: 201, json: { id: "new", kind: "new_skill" } });
        }
        return route.fulfill({ json: [{ id: "python", name: "Python", aliases: ["CPython"], category: "hard" }] });
      });
      await page.route("**/api/profile/skills/python/aliases", async (route) => {
        expect(route.request().postDataJSON()).toEqual({ alias: "Python3" });
        aliasSaved = true;
        await route.fulfill({ status: 201, json: { id: "alias", kind: "alias" } });
      });

      await page.goto("/shortlist");
      await page.getByText("Staff Engineer", { exact: true }).click();
      const addRust = page.getByRole("button", { name: chinese ? "将“Rust programming”添加到你的个人资料" : 'Add "Rust programming" to your profile' });
      await addRust.click();
      const editor = page.getByRole("dialog", { name: chinese ? "添加技能" : "Add a skill", exact: true });
      await expect(editor.getByLabel(chinese ? "技能名称" : "Skill name", { exact: true })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(editor).toHaveCount(0);
      await expect(addRust).toBeFocused();
      await addRust.click();
      await editor.getByLabel(chinese ? "技能名称" : "Skill name", { exact: true }).fill("Rust");
      await editor.getByLabel(chinese ? "别名" : "Aliases", { exact: true }).fill("rustlang");
      await editor.getByLabel(chinese ? "分组" : "Group", { exact: true }).selectOption("languages");
      const newTab = editor.getByRole("tab", { name: chinese ? "新建技能" : "New skill", exact: true });
      await newTab.focus();
      await page.keyboard.press("ArrowRight");
      const aliasTab = editor.getByRole("tab", { name: chinese ? "关联已有技能" : "Use existing skill" });
      await expect(aliasTab).toBeFocused();
      await newTab.click();
      await expect(editor.getByLabel(chinese ? "技能名称" : "Skill name", { exact: true })).toHaveValue("Rust");
      await expect(editor).toBeInViewport({ ratio: 1 });
      expect(await editor.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`job-skill-new-${language}-${width}.png`) });
      await editor.getByRole("button", { name: chinese ? "添加技能" : "Add skill", exact: true }).click();
      await expect(editor).toHaveCount(0);
      expect(newSkill).toEqual({ name: "Rust", aliases: ["rustlang", "Rust programming"], category: "hard", group: "languages" });
      await expect(addRust).toHaveCount(0);

      const addPython = page.getByRole("button", { name: chinese ? "将“Python3”添加到你的个人资料" : 'Add "Python3" to your profile' });
      await addPython.click();
      await editor.getByRole("tab", { name: chinese ? "关联已有技能" : "Use existing skill" }).click();
      await editor.getByRole("textbox", { name: chinese ? "搜索技能和别名" : "Search skills and aliases" }).fill("cpython");
      const python = editor.getByRole("button", { name: /Python/ });
      await expect(python).toBeVisible();
      await expect(editor).toBeInViewport({ ratio: 1 });
      expect(await editor.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`job-skill-alias-${language}-${width}.png`) });
      await python.click();
      await expect(editor).toHaveCount(0);
      await expect(addPython).toHaveCount(0);
      await expect(page.getByRole("dialog").locator('.skill-chip[data-covered="true"]')).toHaveCount(2);
      expect(errors).toEqual([]);
    });
  }
}
