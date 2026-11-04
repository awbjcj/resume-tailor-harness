import { render, screen } from "@testing-library/react";
import { Compass } from "lucide-react";
import { describe, expect, it } from "vitest";

import { GuidedWorkspaceHeader } from "./GuidedWorkspaceHeader";

describe("GuidedWorkspaceHeader", () => {
  it("renders semantic title, metadata, actions, and tone", () => {
    const { container } = render(
      <GuidedWorkspaceHeader
        tone="scout"
        icon={<Compass />}
        title="Discovery Scout"
        meta={<span>4 pending</span>}
        actions={<button type="button">End session</button>}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Discovery Scout" })).toBeInTheDocument();
    expect(screen.getByText("4 pending")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "End session" })).toBeInTheDocument();
    expect(container.querySelector(".guided-workspace-icon")).toHaveAttribute("data-tone", "scout");
    expect(screen.getAllByText("Discovery Scout")).toHaveLength(1);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("supports the Career Lab tone", () => {
    render(
      <GuidedWorkspaceHeader
        tone="career-lab"
        icon={<Compass />}
        title="Career Lab"
      />,
    );
    expect(screen.getByRole("heading", { name: "Career Lab" }).querySelector(".guided-workspace-icon")).toHaveAttribute(
      "data-tone",
      "career-lab",
    );
  });
});
