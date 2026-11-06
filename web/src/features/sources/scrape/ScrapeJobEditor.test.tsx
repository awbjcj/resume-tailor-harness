import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ScrapeJobEditor } from "./ScrapeJobEditor";
import type { JobFacts } from "./use-scrape";

describe("scraped job corrections", () => {
  it("lets users explicitly clear a work policy to unknown", async () => {
    function Editor() {
      const [value, setValue] = useState<JobFacts>({
        sourceUrl: "https://example.com/job",
        remotePolicy: "remote",
      });
      return (
        <>
          <ScrapeJobEditor value={value} onChange={setValue} />
          <output>{value.remotePolicy ?? "unknown"}</output>
        </>
      );
    }
    render(<Editor />);
    await userEvent.selectOptions(screen.getByLabelText("Work policy"), "");
    expect(screen.getByRole("status")).toHaveTextContent("unknown");
  });

  it("edits existing job and salary location labels independently", async () => {
    const user = userEvent.setup();
    const change = vi.fn();
    const facts: JobFacts = {
      sourceUrl: "https://example.com/job",
      locations: ["Austin, TX"],
      salaryBands: [{ rawText: "$100k", locations: ["Seattle, WA"] }],
    };
    render(<ScrapeJobEditor value={facts} onChange={change} />);
    await user.click(screen.getByRole("button", { name: "Remove Austin, TX" }));
    expect(change).toHaveBeenLastCalledWith({ ...facts, locations: null });
    await user.type(screen.getByLabelText("Salary locations"), "Toronto, ON{Enter}");
    expect(change).toHaveBeenLastCalledWith({
      ...facts,
      salaryBands: [{ rawText: "$100k", locations: ["Seattle, WA", "Toronto, ON"] }],
    });
  });

  it("keeps the remaining salary band's draft when the preceding band is deleted", async () => {
    const user = userEvent.setup();
    function Editor() {
      const [value, setValue] = useState<JobFacts>({
        sourceUrl: "https://example.com/job",
        salaryBands: [{ rawText: "First" }, { rawText: "Second" }],
      });
      return <ScrapeJobEditor value={value} onChange={setValue} />;
    }
    render(<Editor />);
    const [first, second] = screen.getAllByLabelText("Salary locations");
    await user.type(first, "Austin, TX");
    await user.type(second, "Seattle, WA");
    await user.click(screen.getAllByRole("button", { name: "Remove salary band" })[0]);
    expect(screen.getByLabelText("Original salary text")).toHaveValue("Second");
    expect(screen.getByLabelText("Salary locations")).toHaveValue("Seattle, WA");
  });
});
