import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { withQueryClient } from "@/test/utils";
import { ScrapeImport } from "./ScrapeImport";

describe("public page import", () => {
  it("offers an editable URL and crawl limits before analysis", async () => {
    render(<ScrapeImport />, { wrapper: withQueryClient });
    await userEvent.click(
      screen.getByRole("button", { name: "Add job board URL" }),
    );
    expect(
      screen.getByRole("button", { name: "Analyze job board" }),
    ).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText("Job board URL"),
      "https://example.com/jobs",
    );
    expect(
      screen.getByRole("button", { name: "Analyze job board" }),
    ).not.toBeDisabled();
    expect(screen.getByLabelText("Job board URL")).toHaveAttribute(
      "maxlength",
      "8192",
    );
    expect(screen.getByLabelText("Job details")).toHaveValue(50);
  });

  it("shows an inline error for an invalid board URL", async () => {
    render(<ScrapeImport />, { wrapper: withQueryClient });
    await userEvent.click(
      screen.getByRole("button", { name: "Add job board URL" }),
    );
    const input = screen.getByLabelText("Job board URL");
    await userEvent.type(input, "example.com/jobs");
    await userEvent.tab();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Enter a complete http(s) URL.")).toBeVisible();
  });
});
