import { useState } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { changeLanguage } from "@/i18n";
import { DeferredDialogBody } from "./DeferredDialogBody";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "./ui/dialog";

function Form() {
  const [value, setValue] = useState("");
  return <DialogContent><DialogTitle>Form</DialogTitle>
    <input aria-label="Draft" value={value} onChange={(event) => setValue(event.target.value)} />
  </DialogContent>;
}

function Harness({ load }: { load: () => Promise<{ default: typeof Form }> }) {
  const [open, setOpen] = useState(false);
  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger>Open form</DialogTrigger>
    <DeferredDialogBody active={open} title="Form" load={load} bodyProps={{}} />
  </Dialog>;
}

it("loads on demand, keeps focus in the dialog, and preserves a closed draft", async () => {
  let resolve!: (module: { default: typeof Form }) => void;
  const load = vi.fn(() => new Promise<{ default: typeof Form }>((done) => { resolve = done; }));
  const user = userEvent.setup();
  render(<Harness load={load} />);
  expect(load).not.toHaveBeenCalled();
  const trigger = screen.getByRole("button", { name: "Open form" });
  await user.click(trigger);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  await act(async () => { resolve({ default: Form }); });
  const input = await screen.findByLabelText("Draft");
  await waitFor(() => expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement));
  await user.type(input, "Keep this draft");
  await user.keyboard("{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
  await user.click(trigger);
  expect(await screen.findByLabelText("Draft")).toHaveValue("Keep this draft");
  expect(load).toHaveBeenCalledTimes(1);
});

it.each(["en", "zh-CN"] as const)("recovers from a failed chunk with localized feedback in %s", async (language) => {
  await changeLanguage(language);
  const load = vi.fn<() => Promise<{ default: typeof Form }>>()
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ default: Form });
  const user = userEvent.setup();
  render(<Harness load={load} />);
  await user.click(screen.getByRole("button", { name: "Open form" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(language === "en" ? "This form could not load" : "无法加载此表单");
  await user.click(screen.getByRole("button", { name: language === "en" ? "Try again" : "重试" }));
  expect(await screen.findByLabelText("Draft")).toBeVisible();
  expect(load).toHaveBeenCalledTimes(2);
});

it("can close while loading without opening again when the import resolves", async () => {
  let resolve!: (module: { default: typeof Form }) => void;
  const load = () => new Promise<{ default: typeof Form }>((done) => { resolve = done; });
  const user = userEvent.setup();
  render(<Harness load={load} />);
  const trigger = screen.getByRole("button", { name: "Open form" });
  await user.click(trigger);
  await user.keyboard("{Escape}");
  await act(async () => { resolve({ default: Form }); });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await waitFor(() => expect(trigger).toHaveFocus());
});
