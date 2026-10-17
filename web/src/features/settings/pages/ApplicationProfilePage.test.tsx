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
    fireEvent.change(screen.getByLabelText("At least 18 years old"), { target: { value: "Yes" } });
    fireEvent.change(screen.getByLabelText("U.S. worker category"), { target: { value: "No" } });
    fireEvent.change(screen.getByLabelText("Verification of legal right to work"), { target: { value: "U.S.: Yes" } });
    fireEvent.change(screen.getByLabelText("Previous applications to each employer"), { target: { value: "Acme: No" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved).toMatchObject({ fullName: "Ada", expectedSalary: "USD 120,000/year", ethnicity: "Prefer not to disclose" }));
    expect(saved).toMatchObject({ atLeast18: "Yes", usWorkerCategory: "No", workAuthorizationVerification: "U.S.: Yes", previousApplications: "Acme: No" });
    await waitFor(() => expect(screen.queryByText(/unsaved changes/i)).not.toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Race / ethnicity"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved.ethnicity).toBe(""));
    await act(() => changeLanguage("zh-CN"));
    expect(screen.getByLabelText("期望薪资")).toHaveValue("USD 120,000/year");
    expect(screen.getByLabelText("种族／族裔")).toHaveValue("");
    expect(screen.getByLabelText("是否年满18岁")).toHaveValue("Yes");
    expect(screen.getByLabelText("美国劳工身份类别")).toHaveValue("No");
    expect(screen.getByLabelText("向各雇主提交过的申请")).toHaveValue("Acme: No");
  });

  it("keeps screening answers unknown until saved and supports discard", async () => {
    let writes = 0;
    server.use(
      http.get("/api/config/application-profile", () => HttpResponse.json({})),
      http.put("/api/config/application-profile", () => { writes += 1; return HttpResponse.json({}); }),
    );
    render(<ApplicationProfilePage />, { wrapper: withQueryClient });
    const citizenship = await screen.findByLabelText("Export-control citizenship / dual citizenship");
    expect(citizenship).toHaveValue("");
    expect(screen.getByLabelText("Current for-profit company board membership")).toHaveValue("");
    expect(screen.getByLabelText("Friends / relatives employed by each employer")).toHaveValue("");
    fireEvent.change(citizenship, { target: { value: "Cuba, Iran, North Korea, Syria: No" } });
    expect(writes).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(citizenship).toHaveValue("");
    expect(writes).toBe(0);
  });
});
