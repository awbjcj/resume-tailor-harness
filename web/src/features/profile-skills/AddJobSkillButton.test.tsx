import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { AddJobSkillButton } from "./AddJobSkillButton";

const matrix = {
  groups: [
    { slug: "languages", label: "Programming Languages", category: "technical" },
    { slug: "custom", label: "My tools", category: "technical", customized: true },
  ],
  categories: [{ slug: "technical", label: "Technical skills" }],
  rows: [],
};

function show(skillName = "Rust") {
  return render(<AddJobSkillButton skillName={skillName} />, { wrapper: withQueryClient });
}

async function open(user: ReturnType<typeof userEvent.setup>, skillName = "Rust") {
  await user.click(screen.getByRole("button", { name: `Add "${skillName}" to your profile` }));
  await screen.findByRole("tab", { name: "New skill" });
  return screen.getByRole("dialog", { name: "Add a skill" });
}

describe("adding a job skill to the personal library", () => {
  beforeEach(() => {
    server.use(http.get("*/api/profile/matrix", () => HttpResponse.json(matrix)));
  });

  it("uses the library editor and saves aliases, type, and group together", async () => {
    const loadMatrix = vi.fn(() => HttpResponse.json(matrix));
    let body: unknown;
    server.use(
      http.get("*/api/profile/matrix", loadMatrix),
      http.post("*/api/profile/skills", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: "new-skill", kind: "new_skill" });
      }),
    );
    const user = userEvent.setup();
    show();
    expect(loadMatrix).not.toHaveBeenCalled();
    await open(user);
    const name = await screen.findByRole("textbox", { name: "Skill name" });
    expect(name).toHaveValue("Rust");
    expect(screen.getByRole("combobox", { name: "Skill type" })).toHaveValue("hard");
    await user.type(screen.getByRole("textbox", { name: "Aliases" }), "rustlang, rustlang\nRust language");
    await user.selectOptions(screen.getByRole("combobox", { name: "Skill type" }), "domain");
    await user.selectOptions(screen.getByRole("combobox", { name: "Group" }), "custom");
    await user.click(screen.getByRole("button", { name: "Add skill" }));
    await waitFor(() => expect(body).toEqual({
      name: "Rust", category: "domain", group: "custom", aliases: ["rustlang", "Rust language"],
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("keeps the extracted wording as an alias when the new skill is renamed", async () => {
    let body: unknown;
    server.use(http.post("*/api/profile/skills", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "new-skill", kind: "new_skill" });
    }));
    const user = userEvent.setup();
    show("Rust programming");
    await open(user, "Rust programming");
    const name = await screen.findByRole("textbox", { name: "Skill name" });
    await user.clear(name);
    await user.type(name, "Rust");
    await user.click(screen.getByRole("button", { name: "Add skill" }));
    await waitFor(() => expect(body).toEqual({
      name: "Rust", category: "hard", group: "", aliases: ["Rust programming"],
    }));
  });

  it("searches existing aliases and appends the job wording to the selected skill", async () => {
    let aliasPath = "";
    let aliasBody: unknown;
    server.use(
      http.get("*/api/profile/skills", () => HttpResponse.json([
        { id: "s1", name: "Python", category: "hard", aliases: ["CPython"] },
        { id: "s2", name: "Rust", category: "hard" },
      ])),
      http.post("*/api/profile/skills/:skillId/aliases", async ({ request, params }) => {
        aliasPath = String(params.skillId);
        aliasBody = await request.json();
        return HttpResponse.json({ id: "alias", kind: "alias" });
      }),
    );
    const user = userEvent.setup();
    show("Python3");
    await open(user, "Python3");
    await user.click(screen.getByRole("tab", { name: "Use existing skill" }));
    await screen.findByRole("button", { name: /Python/ });
    await user.type(screen.getByRole("textbox", { name: "Search skills and aliases" }), "  cpython");
    expect(screen.queryByRole("button", { name: /Rust/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Python/ }));
    await waitFor(() => expect(aliasPath).toBe("s1"));
    expect(aliasBody).toEqual({ alias: "Python3" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("keeps new-skill edits when switching between the two operations", async () => {
    server.use(http.get("*/api/profile/skills", () => HttpResponse.json([])));
    const user = userEvent.setup();
    show();
    await open(user);
    await user.type(await screen.findByRole("textbox", { name: "Aliases" }), "rustlang");
    await user.selectOptions(screen.getByRole("combobox", { name: "Group" }), "custom");
    await user.click(screen.getByRole("tab", { name: "Use existing skill" }));
    await screen.findByText("No personal skills yet. Add this as a new skill.");
    await user.click(screen.getByRole("tab", { name: "New skill" }));
    expect(screen.getByRole("textbox", { name: "Aliases" })).toHaveValue("rustlang");
    expect(screen.getByRole("combobox", { name: "Group" })).toHaveValue("custom");
  });

  it("shows an inline save failure and lets the user correct and retry", async () => {
    server.use(http.post("*/api/profile/skills", () =>
      HttpResponse.json({ error: { code: "VALIDATION_ERROR", message: "Skill already exists" } }, { status: 422 }),
    ));
    const user = userEvent.setup();
    show();
    await open(user);
    await screen.findByRole("textbox", { name: "Skill name" });
    await user.click(screen.getByRole("button", { name: "Add skill" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Skill already exists");
    expect(screen.getByRole("textbox", { name: "Skill name" })).toHaveValue("Rust");
    server.use(http.post("*/api/profile/skills", () => HttpResponse.json({ id: "new-skill" })));
    await user.click(screen.getByRole("button", { name: "Add skill" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("recovers from a failed library read before choosing a group", async () => {
    server.use(http.get("*/api/profile/matrix", () =>
      HttpResponse.json({ error: { message: "Unavailable" } }, { status: 503 }),
    ));
    const user = userEvent.setup();
    show();
    await open(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load the skill matrix");
    expect(screen.queryByRole("button", { name: "Add skill" })).not.toBeInTheDocument();
    server.use(http.get("*/api/profile/matrix", () => HttpResponse.json(matrix)));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("combobox", { name: "Group" })).toHaveValue("");
  });

  it("distinguishes a failed alias-target read from an empty library and allows retry", async () => {
    server.use(http.get("*/api/profile/skills", () =>
      HttpResponse.json({ error: { message: "Unavailable" } }, { status: 503 }),
    ));
    const user = userEvent.setup();
    show();
    await open(user);
    await user.click(screen.getByRole("tab", { name: "Use existing skill" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your skills.");
    server.use(http.get("*/api/profile/skills", () => HttpResponse.json([])));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("status")).toHaveTextContent("No personal skills yet.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("prevents duplicate saves, switching operations, and dismissal while saving", async () => {
    let finish!: () => void;
    const ready = new Promise<void>((resolve) => { finish = resolve; });
    const save = vi.fn(async () => { await ready; return HttpResponse.json({ id: "new-skill" }); });
    server.use(http.post("*/api/profile/skills", save));
    const user = userEvent.setup();
    show();
    await open(user);
    await screen.findByRole("textbox", { name: "Skill name" });
    await user.click(screen.getByRole("button", { name: "Add skill" }));
    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("tab", { name: "Use existing skill" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(save).toHaveBeenCalledOnce();
    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("returns focus to the job chip and resets the draft after cancelling", async () => {
    const user = userEvent.setup();
    show();
    await open(user);
    await user.type(await screen.findByRole("textbox", { name: "Aliases" }), "temporary");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    const trigger = screen.getByRole("button", { name: 'Add "Rust" to your profile' });
    await waitFor(() => expect(trigger).toHaveFocus());
    await user.click(trigger);
    expect(await screen.findByRole("textbox", { name: "Aliases" })).toHaveValue("");
  });

  it("updates the complete open workflow when the interface language changes", async () => {
    const user = userEvent.setup();
    show();
    const dialog = await open(user);
    await screen.findByRole("combobox", { name: "Group" });
    await act(async () => { await changeLanguage("zh-CN"); });
    expect(within(dialog).getByRole("tab", { name: "关联已有技能" })).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "技能名称" })).toHaveValue("Rust");
    expect(within(dialog).getByRole("option", { name: "编程语言" })).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: "My tools" })).toBeInTheDocument();
    expect(within(dialog).getByRole("combobox", { name: "技能类型" })).toHaveValue("hard");
  });
});
