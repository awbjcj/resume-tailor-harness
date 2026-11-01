import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { DraftNoteCard } from "./DraftNoteCard";
import type { CoachDraftNote } from "./use-coach";

const note: CoachDraftNote = {
  topicId: "t1", title: "Platform ownership", summary: "Led the migration.",
  quotes: ["I led the platform migration."], status: "pending",
};

describe("DraftNoteCard", () => {
  it("saves the edited note only on request, locks controls in flight, and retains edits after a failure", async () => {
    const user = userEvent.setup();
    let reject!: (cause: Error) => void;
    const save = vi.fn(() => new Promise<void>((_done, fail) => { reject = fail; }));
    render(<DraftNoteCard note={note} saving={false} discarding={false} onSave={save} onDiscard={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Edit note" }));
    await user.clear(screen.getByRole("textbox", { name: "Title" }));
    await user.type(screen.getByRole("textbox", { name: "Title" }), "  Migration ownership  ");
    expect(save).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Save note" }));
    expect(screen.getByRole("textbox", { name: "Title" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard" })).toBeDisabled();
    expect(save).toHaveBeenCalledExactlyOnceWith({ ...note, title: "Migration ownership" });
    await act(async () => reject(new Error("Unavailable")));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your draft is kept");
    expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("  Migration ownership  ");
    expect(screen.getByRole("button", { name: "Save note" })).toBeEnabled();
  });

  it("can cancel discard without losing edits and submits only the confirmed discard", async () => {
    const user = userEvent.setup();
    const discard = vi.fn();
    render(<DraftNoteCard note={note} saving={false} discarding={false} onSave={vi.fn()} onDiscard={discard} />);
    await user.click(screen.getByRole("button", { name: "Edit note" }));
    await user.type(screen.getByRole("textbox", { name: "Summary" }), " Improved the handover.");
    await user.click(screen.getByRole("button", { name: "Discard" }));
    expect(discard).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Keep draft" }));
    expect(screen.getByRole("textbox", { name: "Summary" })).toHaveValue("Led the migration. Improved the handover.");
    await user.click(screen.getByRole("button", { name: "Discard" }));
    await user.click(screen.getByRole("button", { name: "Discard" }));
    expect(discard).toHaveBeenCalledTimes(1);
  });

  it("explains why a note without evidence cannot be saved", () => {
    render(<DraftNoteCard note={{ ...note, quotes: [" "] }} saving={false} discarding={false} onSave={vi.fn()} onDiscard={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Save note" })).toBeDisabled();
    expect(screen.getByText(/needs supporting evidence/)).toBeInTheDocument();
  });

  it("disables all decisions while another conversation action is running", () => {
    render(<DraftNoteCard note={note} busy saving={false} discarding={false} onSave={vi.fn()} onDiscard={vi.fn()} />);
    for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
  });

  it("updates field labels and saved state when switching language without translating the note", async () => {
    const view = render(<DraftNoteCard note={note} saving={false} discarding={false} onSave={vi.fn()} onDiscard={vi.fn()} />);
    await act(async () => { await changeLanguage("zh-CN"); });
    await userEvent.click(screen.getByRole("button", { name: "编辑笔记" }));
    expect(screen.getByRole("textbox", { name: "标题" })).toHaveValue(note.title);
    expect(screen.getByRole("button", { name: "保存笔记" })).toBeInTheDocument();
    view.rerender(<DraftNoteCard note={{ ...note, status: "saved" }} saving={false} discarding={false} onSave={vi.fn()} onDiscard={vi.fn()} />);
    expect(screen.getByText("已加入个人资料")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
