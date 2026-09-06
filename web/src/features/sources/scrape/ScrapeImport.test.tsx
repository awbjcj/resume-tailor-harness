import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { withQueryClient } from "@/test/utils";
import { ScrapeImport } from "./ScrapeImport";

describe("public page import", () => {
  it("offers an editable URL and crawl limits before analysis", async () => {
    render(<ScrapeImport />, { wrapper: withQueryClient });
    await userEvent.click(
      screen.getByRole("button", { name: "Import public page" }),
    );
    expect(screen.getByRole("button", { name: "Analyze page" })).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText("Public job or board URL"),
      "https://example.com/jobs",
    );
    expect(
      screen.getByRole("button", { name: "Analyze page" }),
    ).not.toBeDisabled();
    expect(screen.getByLabelText("Job details")).toHaveValue(50);
  });
});
