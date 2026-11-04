import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("keeps one page title alongside useful metadata and actions", () => {
    render(
      <PageHeader title="Shortlist" meta={<span>12 jobs</span>} actions={<button>Review jobs</button>} />,
    );

    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("Shortlist");
    expect(screen.getAllByRole("heading")).toHaveLength(1);
    expect(screen.getByText("12 jobs")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review jobs" })).toBeInTheDocument();
  });
});
