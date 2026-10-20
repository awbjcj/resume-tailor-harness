import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TextPart } from "./TextPart";

describe("TextPart", () => {
  it("renders structured Markdown with accessible overflow surfaces", () => {
    render(<TextPart text={'## Plan\n\n1. Review **evidence**\n2. Prepare `notes`\n\n| Role | Fit |\n| --- | --- |\n| Engineer | Strong |\n\n```ts\nconst next = "review";\n```'} />);
    expect(screen.getByRole("heading", { level: 2, name: "Plan" })).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("region", { name: "Table" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("table")).toHaveTextContent("Engineer");
    expect(screen.getByLabelText("Code block")).toHaveAttribute("tabindex", "0");
    expect(screen.getByLabelText("Code block")).toHaveTextContent('const next = "review";');
  });

  it("removes streaming feedback when the response settles without remounting prose", () => {
    const { rerender } = render(<TextPart text="Keep this answer readable." caret />);
    const prose = screen.getByText("Keep this answer readable.");
    expect(screen.getByTestId("chat-stream-caret")).toHaveAttribute("aria-hidden", "true");
    rerender(<TextPart text="Keep this answer readable." />);
    expect(screen.queryByTestId("chat-stream-caret")).not.toBeInTheDocument();
    expect(screen.getByText("Keep this answer readable.")).toBe(prose);
  });
});
