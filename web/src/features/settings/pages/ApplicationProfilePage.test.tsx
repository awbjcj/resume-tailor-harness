import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { ApplicationProfilePage } from "./ApplicationProfilePage";
import { changeLanguage } from "@/i18n";

describe("ApplicationProfilePage", () => {
  it("saves optional answers, preserves other fields, and supports clearing", async () => {
    let saved: Record<string, string> = { fullName: "Ada", ethnicity: "", veteranStatus: "" };
    server.use(
      http.get("/api/config/application-profile", () => HttpResponse.json(saved)),
      http.put("/api/config/application-profile", async ({ request }) => {
        saved = await request.json() as Record<string, string>;
        return HttpResponse.json(saved);
      }),
    );
    render(<ApplicationProfilePage />, { wrapper: withQueryClient });
    expect(await screen.findByLabelText("Full name")).toHaveValue("Ada");
    expect(screen.getByLabelText("Veteran status")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Expected salary"), { target: { value: "USD 120,000/year" } });
    fireEvent.change(screen.getByLabelText("Race / ethnicity"), { target: { value: "Prefer not to disclose" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved).toMatchObject({ fullName: "Ada", expectedSalary: "USD 120,000/year", ethnicity: "Prefer not to disclose" }));
    await waitFor(() => expect(screen.queryByText(/unsaved changes/i)).not.toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Race / ethnicity"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved.ethnicity).toBe(""));
    await act(() => changeLanguage("zh-CN"));
    expect(screen.getByLabelText("期望薪资")).toHaveValue("USD 120,000/year");
    expect(screen.getByLabelText("种族／族裔")).toHaveValue("");
  });
});
