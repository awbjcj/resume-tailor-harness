import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { ManualJobDialog } from "./ManualJobDialog";

async function openForm() {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  render(<ManualJobDialog />, { wrapper });
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Add job manually" }));
  await screen.findByLabelText("Job title *");
  return { user, invalidate };
}

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Job title *"), "Platform Engineer");
  await user.type(screen.getByLabelText("Company *"), "Acme");
  await user.type(screen.getByLabelText("Full job description *"), "Build and maintain Python services.");
}

it("validates fields, preserves drafts through server failures, and refreshes boards after retry", async () => {
  let body: Record<string, unknown> | undefined;
  let status = 201;
  const post = vi.fn(async ({ request }: { request: Request }) => {
    body = await request.json() as Record<string, unknown>;
    if (status !== 201) {
      return HttpResponse.json({ error: { code: "FAILED", message: `HTTP ${status}` } }, { status });
    }
    return HttpResponse.json({ id: 42, title: "Platform Engineer", company: "Acme" }, { status: 201 });
  });
  server.use(http.post("/api/jobs", post));
  const { user, invalidate } = await openForm();
  await fillRequired(user);
  await user.clear(screen.getByLabelText("Job title *"));
  await user.type(screen.getByLabelText("Job title *"), "   ");
  await user.click(screen.getByRole("button", { name: "Save job" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Enter a job title");
  await user.type(screen.getByLabelText("Job title *"), "Platform Engineer");
  await user.type(screen.getByLabelText("Minimum salary"), "200");
  await user.type(screen.getByLabelText("Maximum salary"), "100");
  await user.click(screen.getByRole("button", { name: "Save job" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("valid salary range"));
  expect(post).not.toHaveBeenCalled();
  await user.clear(screen.getByLabelText("Job title *"));
  await user.type(screen.getByLabelText("Job title *"), "Platform Engineer");
  await user.clear(screen.getByLabelText("Minimum salary"));
  await user.clear(screen.getByLabelText("Maximum salary"));
  await user.type(screen.getByLabelText("Job posting URL"), "https://example.com/jobs/42");
  await user.selectOptions(screen.getByLabelText("Work arrangement"), "hybrid");
  await user.selectOptions(screen.getByLabelText("Employment type"), "full_time");
  await user.type(screen.getByLabelText("Minimum salary"), "120000");
  await user.type(screen.getByLabelText("Maximum salary"), "160000");
  await user.type(screen.getByLabelText("Currency (3-letter code)"), "usd");
  await user.selectOptions(screen.getByLabelText("Pay period"), "year");
  await user.type(screen.getByLabelText("Required skills"), "Python\nSQL");
  for (const [failure, message] of [
    [409, /already exists/i],
    [429, /limit|quota/i],
    [500, /could not|failed|unable/i],
  ] as const) {
    status = failure;
    await user.click(screen.getByRole("button", { name: "Save job" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(message));
    expect(screen.getByLabelText("Job title *"), `draft after HTTP ${failure}`).toHaveValue("Platform Engineer");
  }
  status = 201;
  await user.click(screen.getByRole("button", { name: "Save job" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Job saved: Platform Engineer at Acme (ID 42).");
  expect(body).toMatchObject({ company: "Acme", postedAt: null, details: {
    remotePolicy: "hybrid", employmentType: "full_time", salaryMin: 120000,
    salaryMax: 160000, salaryCurrency: "USD", salaryPeriod: "year", mustHaveSkills: ["Python", "SQL"],
  } });
  expect(screen.getByRole("link", { name: "View saved job" })).toHaveAttribute("href", "/triage?job=42");
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["triage"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard-summary"] });
  await user.click(screen.getByRole("button", { name: "Add another job" }));
  expect(screen.getByLabelText("Job title *")).toHaveValue("");
});
