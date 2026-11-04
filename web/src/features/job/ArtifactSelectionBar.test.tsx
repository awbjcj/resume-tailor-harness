import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { ArtifactSelectionBar } from "./ArtifactSelectionBar";

it.each([
  ["version", "选择所有可删除的简历版本", "删除 2 个简历版本？", "Delete 2 versions?"],
  ["coverLetter", "选择所有可删除的求职信", "删除 2 封求职信？", "Delete 2 cover letters?"],
] as const)("keeps the selected %s and deletion confirmation clear across languages", async (kind, selectAll, title, englishTitle) => {
  await changeLanguage("zh-CN");
  const onDelete = vi.fn();
  const user = userEvent.setup();
  render(<ArtifactSelectionBar kind={kind} selectedCount={2} allSelected onToggleAll={vi.fn()} onDelete={onDelete} />);

  expect(screen.getByRole("checkbox", { name: selectAll })).toBeChecked();
  await user.click(screen.getByRole("button", { name: "删除所选（2）" }));
  expect(screen.getByRole("alertdialog", { name: title })).toHaveTextContent("此操作无法撤销");

  await act(() => changeLanguage("en"));
  const dialog = screen.getByRole("alertdialog", { name: englishTitle });
  await user.click(within(dialog).getByRole("button", { name: "Confirm delete" }));
  expect(onDelete).toHaveBeenCalledOnce();
});
