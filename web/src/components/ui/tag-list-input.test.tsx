import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { TagListInput } from "./tag-list-input";

function Harness() {
  const [value, setValue] = useState<string[]>([]);
  return (
    <>
      <TagListInput id="tags" label="Tags" value={value} onChange={setValue} />
      <output data-testid="tags">{value.join("|")}</output>
    </>
  );
}

describe("TagListInput", () => {
  it("adds with Enter or the Add button, trims pasted tags, and drops empty and duplicate segments", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("textbox");
    await user.type(input, "python{Enter}");
    expect(screen.getByTestId("tags")).toHaveTextContent("python");
    await user.click(input);
    await user.paste("python,, python , django");
    await user.tab();
    expect(screen.getByTestId("tags")).toHaveTextContent(/^python$/);
    await user.click(screen.getByRole("button", { name: "Add to Tags" }));
    expect(screen.getByTestId("tags")).toHaveTextContent("python|django");
    await user.click(screen.getByRole("button", { name: "Remove python" }));
    await user.click(screen.getByRole("button", { name: "Remove django" }));
    await user.click(input);
    await user.paste("Python, Django\r\n Kubernetes，Go");
    expect(screen.getByTestId("tags")).toHaveTextContent(
      "Python|Django|Kubernetes|Go"
    );
  });

  it("keeps commas in a location and keeps Enter from submitting the form", async () => {
    const user = userEvent.setup();
    const change = vi.fn();
    const submit = vi.fn((event) => event.preventDefault());
    render(
      <form onSubmit={submit}>
        <TagListInput id="locations" label="Locations" value={["Berlin"]} onChange={change} separator="semicolon" />
        <button type="submit">Save</button>
      </form>,
    );
    const input = screen.getByLabelText("Locations");
    await user.type(input, "Austin, TX; Toronto, ON{Enter}");
    expect(change).toHaveBeenCalledOnce();
    expect(change).toHaveBeenLastCalledWith(["Berlin", "Austin, TX", "Toronto, ON"]);
    expect(submit).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Remove Berlin" }));
    expect(change).toHaveBeenLastCalledWith([]);
    expect(input).toHaveFocus();
  });

  it("stops native form submission when a typed value still needs to be added", async () => {
    const user = userEvent.setup();
    const submit = vi.fn((event) => event.preventDefault());
    render(
      <form onSubmit={submit}>
        <Harness />
        <button type="submit">Save</button>
      </form>,
    );
    const input = screen.getByLabelText("Tags");
    const save = screen.getByRole("button", { name: "Save" });
    await user.type(input, "Python");
    await user.click(save);
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Press Enter or use Add to add your entry, or clear the field before saving.");
    await user.click(screen.getByRole("button", { name: "Add to Tags" }));
    await user.click(save);
    expect(submit).toHaveBeenCalledOnce();
  });

  it("explains how to add an entry before saving in Chinese", async () => {
    await changeLanguage("zh-CN");
    const user = userEvent.setup();
    const submit = vi.fn((event) => event.preventDefault());
    render(
      <form onSubmit={submit}>
        <TagListInput id="skills" label="技能" value={[]} onChange={vi.fn()} />
        <button type="submit">保存</button>
      </form>,
    );

    await user.type(screen.getByLabelText("技能"), "Python");
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("保存前，请按 Enter 或点击“添加”来添加输入内容，或清空输入框。");
    expect(screen.getByRole("button", { name: "添加到技能" })).toBeEnabled();
  });

  it("keeps an invalid pasted list available for correction", async () => {
    const user = userEvent.setup();
    const change = vi.fn();
    render(
      <TagListInput id="ids" label="IDs" value={[]} onChange={change}
        validation={{ parse: (text) => /^\d+$/.test(text) ? text : null, message: "Enter an ID." }} />,
    );
    const input = screen.getByLabelText("IDs");
    await user.click(input);
    await user.paste("42\ninvalid");
    expect(change).not.toHaveBeenCalled();
    expect(input).toHaveValue("42, invalid");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter an ID.");
  });
});
