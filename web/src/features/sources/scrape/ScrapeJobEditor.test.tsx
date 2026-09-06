import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
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
});
