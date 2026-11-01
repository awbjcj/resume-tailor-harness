import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { TagListInput } from "./TagListInput";

function Harness() {
  const [value, setValue] = useState<string[]>([]);
  return (
    <>
      <TagListInput id="tags" value={value} onChange={setValue} />
      <output data-testid="tags">{value.join("|")}</output>
    </>
  );
}

describe("TagListInput", () => {
  it("commits words, trims pasted tags, and drops empty and duplicate segments", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("textbox");
    await user.type(input, "python{Enter}");
    expect(screen.getByTestId("tags")).toHaveTextContent("python");
    await user.click(input);
    await user.paste("python,, python , django");
    await user.tab();
    expect(screen.getByTestId("tags")).toHaveTextContent("python|django");
    await user.click(screen.getByRole("button", { name: "Remove python" }));
    await user.click(screen.getByRole("button", { name: "Remove django" }));
    await user.click(input);
    await user.paste("Python, Django , Kubernetes,Go");
    await user.tab();
    expect(screen.getByTestId("tags")).toHaveTextContent(
      "Python|Django|Kubernetes|Go"
    );
  });
});
