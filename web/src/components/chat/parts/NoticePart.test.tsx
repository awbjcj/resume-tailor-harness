import { act, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { NoticePart } from "./NoticePart";

it("switches a known chat warning between languages and preserves unfamiliar messages", async () => {
  const message = "Some turn details could not be read, so the interview plan was unchanged.";
  await changeLanguage("zh-CN");
  const { rerender } = render(<NoticePart message={message} />);
  expect(await screen.findByText("无法读取本轮的部分内容，面试计划未更改。")).toBeInTheDocument();
  rerender(<NoticePart message="A custom message." />);
  expect(screen.getByText("A custom message.")).toBeInTheDocument();
  rerender(<NoticePart message={message} />);
  await act(() => changeLanguage("en"));
  expect(screen.getByText("Some details from this turn couldn't be read, so the interview plan stayed the same.")).toBeInTheDocument();
});
