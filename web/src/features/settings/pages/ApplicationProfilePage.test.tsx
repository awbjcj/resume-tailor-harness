import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    act(() => {
      fireEvent.change(screen.getByLabelText("Years of industry experience"), { target: { value: "3 years, confirmed 2026-10-23" } });
      fireEvent.change(screen.getByLabelText("Coding time preference"), { target: { value: "80%" } });
      fireEvent.change(screen.getByLabelText("Preferred technical domain"), { target: { value: "Full Stack" } });
      fireEvent.change(screen.getByLabelText("Office attendance"), { target: { value: "U.S., Example City, 3 days/week: Yes" } });
      fireEvent.change(screen.getByLabelText("Other employer-specific screening answers"), { target: { value: "Acme / REQ-1: start 2026-11-23" } });
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved).toMatchObject({ fullName: "Ada", expectedSalary: "USD 120,000/year", ethnicity: "Prefer not to disclose" }));
    expect(saved).toMatchObject({ atLeast18: "Yes", usWorkerCategory: "No", workAuthorizationVerification: "U.S.: Yes", previousApplications: "Acme: No" });
    expect(saved).toMatchObject({ industryExperience: "3 years, confirmed 2026-10-23", codingPreference: "80%", technicalDomain: "Full Stack", officeAttendance: "U.S., Example City, 3 days/week: Yes", employerScreeningAnswers: "Acme / REQ-1: start 2026-11-23" });
    await waitFor(() => expect(screen.queryByText(/unsaved changes/i)).not.toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Race / ethnicity"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved.ethnicity).toBe(""));
    await act(() => changeLanguage("zh-CN"));
    expect(screen.getByLabelText("期望薪资")).toHaveValue("USD 120,000/year");
    expect(screen.getByLabelText("种族／族裔")).toHaveValue("");
    expect(screen.getByLabelText("是否年满 18 岁")).toHaveValue("Yes");
    expect(screen.getByLabelText("美国劳工身份类别")).toHaveValue("No");
    expect(screen.getByLabelText("向各雇主提交过的申请")).toHaveValue("Acme: No");
    expect(screen.getByLabelText("行业工作年限")).toHaveValue("3 years, confirmed 2026-10-23");
    expect(screen.getByLabelText("偏好的编程时间比例")).toHaveValue("80%");
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
    expect(screen.getByLabelText("Years of industry experience")).toHaveValue("");
    expect(screen.getByLabelText("Coding time preference")).toHaveValue("");
    expect(screen.getByLabelText("Preferred technical domain")).toHaveValue("");
    expect(screen.getByLabelText("Office attendance")).toHaveValue("");
    expect(screen.getByLabelText("Other employer-specific screening answers")).toHaveValue("");
    fireEvent.change(citizenship, { target: { value: "Cuba, Iran, North Korea, Syria: No" } });
    expect(writes).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(citizenship).toHaveValue("");
    expect(writes).toBe(0);
  });

  it("saves scoped records without converting unknown answers to No and supports removal", async () => {
    let saved: Record<string, unknown> = { fullName: "Ada", additionalAnswers: "Keep existing notes" };
    server.use(
      http.get("/api/config/application-profile", () => HttpResponse.json(saved)),
      http.put("/api/config/application-profile", async ({ request }) => {
        saved = await request.json() as Record<string, unknown>;
        return HttpResponse.json(saved);
      }),
    );
    render(<ApplicationProfilePage />, { wrapper: withQueryClient });
    expect(await screen.findByLabelText("AI-assisted candidate matching")).toHaveValue("unknown");
    expect(screen.getByLabelText("Sex (optional self-identification)")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Sex (optional self-identification)"), { target: { value: "Male" } });
    fireEvent.change(screen.getByLabelText("AI-assisted candidate matching"), { target: { value: "opt_in" } });
    fireEvent.change(screen.getByLabelText("AI matching preference confirmation date"), { target: { value: "2026-10-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Add country eligibility" }));
    const country = within(screen.getByRole("group", { name: "Work eligibility by country 1" }));
    expect(country.getByLabelText("Legally authorized to work")).toHaveValue("unknown");
    expect(country.getByLabelText("Currently on OPT")).toHaveValue("unknown");
    fireEvent.change(country.getByLabelText(/^Country/), { target: { value: "US" } });
    fireEvent.change(country.getByLabelText("Immigration status"), { target: { value: "H-1B" } });
    fireEvent.change(country.getByLabelText("Currently on OPT"), { target: { value: "no" } });
    fireEvent.change(country.getByLabelText(/^Confirmation date/), { target: { value: "2026-10-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Add employer answer" }));
    const employer = within(screen.getByRole("group", { name: "Scoped employer answer records 1" }));
    fireEvent.change(employer.getByLabelText(/^Employer/), { target: { value: "Acme" } });
    fireEvent.change(employer.getByLabelText("Requisition / role ID"), { target: { value: "REQ-42" } });
    fireEvent.change(employer.getByLabelText(/^Exact question/), { target: { value: "Previously employed here?" } });
    fireEvent.change(employer.getByLabelText("Applicable timeframe"), { target: { value: "Ever" } });
    fireEvent.change(employer.getByLabelText(/^Confirmation date/), { target: { value: "2026-10-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved).toMatchObject({
      fullName: "Ada", additionalAnswers: "Keep existing notes", sex: "Male", aiMatchingPreference: "opt_in",
      aiMatchingConfirmedOn: "2026-10-20",
      workEligibility: [{ country: "US", immigrationStatus: "H-1B", currentlyOnOpt: false, confirmedOn: "2026-10-20" }],
      employerAnswers: [{ employer: "Acme", requisition: "REQ-42", question: "Previously employed here?", answer: null, timeframe: "Ever" }],
    }));
    expect((saved.workEligibility as Record<string, unknown>[])[0].authorizedToWork).toBeUndefined();
    await waitFor(() => expect(screen.queryByText(/unsaved changes/i)).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Remove country eligibility" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved.workEligibility).toEqual([]));
    expect((saved.employerAnswers as unknown[])).toHaveLength(1);
  });

  it("requires scope and confirmation dates before saving a new record and can discard it", async () => {
    let writes = 0;
    server.use(
      http.get("/api/config/application-profile", () => HttpResponse.json({ gender: "Saved gender" })),
      http.put("/api/config/application-profile", () => { writes += 1; return HttpResponse.json({}); }),
    );
    render(<ApplicationProfilePage />, { wrapper: withQueryClient });
    fireEvent.click(await screen.findByRole("button", { name: "Add alternate email" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(writes).toBe(0);
    expect(screen.getByLabelText(/^Alternate email/)).toBeInvalid();
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.queryByRole("button", { name: "Remove alternate email" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Gender")).toHaveValue("Saved gender");
    expect(screen.getByLabelText("Sex (optional self-identification)")).toHaveValue("");
  });
});
