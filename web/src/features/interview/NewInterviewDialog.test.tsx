import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import { server } from "@/test/server";
import { NewInterviewDialog } from "./NewInterviewDialog";

it("waits for sessions before offering jobs and excludes active interviews after retry", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let attempts = 0;
  server.use(
    http.get("/api/pipeline", ({ request }) => HttpResponse.json({
      data: new URL(request.url).searchParams.get("status") === "tailored" ? [
        { jobId: 11, company: "Acme", title: "Staff Engineer", status: "tailored" },
        { jobId: 12, company: "Globex", title: "Platform Engineer", status: "tailored" },
      ] : [],
      pagination: { totalPages: 1 },
    })),
    http.get("/api/interview/sessions", () => {
      attempts += 1;
      return attempts === 1
        ? HttpResponse.json({}, { status: 503 })
        : HttpResponse.json({ sessions: [{ status: "active", jobId: 11 }] });
    }),
  );
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <NewInterviewDialog open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load jobs");
  await waitFor(() => expect(client.getQueryData(["interviewable-jobs"])).toHaveLength(2));
  expect(screen.queryByLabelText("Job")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Try again" }));
  await user.click(await screen.findByLabelText("Job"));
  expect(await screen.findByRole("option", { name: /Globex/ })).toBeVisible();
  expect(screen.queryByRole("option", { name: /Acme/ })).not.toBeInTheDocument();
});
