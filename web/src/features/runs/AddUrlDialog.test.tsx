import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { withQueryClient } from "@/test/utils";
import { AddUrlDialog } from "./AddUrlDialog";

describe("add job URL dialog", () => {
  it("bounds and validates the job posting URL", async () => {
    const user = userEvent.setup();
    render(<AddUrlDialog />, { wrapper: withQueryClient });

    await user.click(screen.getByRole("button", { name: "Add job URL" }));
    const input = screen.getByLabelText("Job posting URL");
    expect(input).toHaveAttribute("maxlength", "8192");

    await user.type(input, "company.com/jobs/role");
    await user.tab();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Enter a complete http(s) URL.")).toBeVisible();
  });
});
