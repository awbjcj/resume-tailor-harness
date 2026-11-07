import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { withQueryClient } from "@/test/utils";
import { SkillMatrix } from "./SkillMatrix";

describe("SkillMatrix", () => {
  it("labels the optional group 'Nice-to-have'", () => {
    render(
      <SkillMatrix
        skills={[
          { name: "Python", required: true, covered: true },
          { name: "Go", required: false, covered: false },
        ]}
      />,
      { wrapper: withQueryClient },
    );
    expect(screen.getByText("Nice-to-have")).toBeInTheDocument();
    expect(screen.queryByText("Best-have")).not.toBeInTheDocument();
  });

  it("renders covered and gap chips sharing the skill-chip class", () => {
    const { container } = render(
      <SkillMatrix
        skills={[
          { name: "Python", required: true, covered: true },
          { name: "Rust", required: true, covered: false },
        ]}
      />,
      { wrapper: withQueryClient },
    );
    expect(container.querySelectorAll(".skill-chip").length).toBe(2);
  });

  it("offers the add action only for skill gaps", () => {
    render(
      <SkillMatrix
        skills={[
          { name: "Python", required: true, covered: true },
          { name: "Rust", required: true, covered: false },
        ]}
      />,
      { wrapper: withQueryClient },
    );
    const [covered, missing] = screen.getAllByRole("listitem");
    expect(within(covered).queryByRole("button")).not.toBeInTheDocument();
    expect(within(missing).getByRole("button", { name: /add "rust"/i })).toBeInTheDocument();
  });
});
