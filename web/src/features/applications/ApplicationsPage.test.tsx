import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { changeLanguage } from "@/i18n";
import { server } from "@/test/server";
import { ApplicationsPage } from "./ApplicationsPage";

const table = {
  technicalRoundColumns: 0,
  rows: [{
    jobId: 42,
    company: "Acme",
    title: "Senior SWE",
    status: "interview",
    source: "greenhouse",
    fitScore: 82,
    overflowRounds: 0,
    customCount: 0,
    totalComp: null,
    compCurrency: null,
    offerDeadline: null,
    cells: {},
  }],
};

function renderPage() {
  server.use(http.get("/api/applications", () => HttpResponse.json(table)));
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><ApplicationsPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ApplicationsPage", () => {
  it("offers a retry when the initial request fails", async () => {
    await changeLanguage("en");
    let requests = 0;
    server.use(http.get("/api/applications", () => {
      requests += 1;
      return requests === 1 ? HttpResponse.json({}, { status: 503 }) : HttpResponse.json(table);
    }));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><ApplicationsPage /></MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load applications");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Acme" })).toBeVisible();
    expect(requests).toBe(2);
  });

  it("paginates long results, then searches all rows and groups matches by status", async () => {
    await changeLanguage("en");
    const rows = Array.from({ length: 42 }, (_, index) => ({
      ...table.rows[0],
      jobId: index + 1,
      company: index === 41 ? "Café Labs" : "Acme",
      title: `Engineer ${index + 1}`,
      status: index === 41 ? "offer" : "interview",
    }));
    server.use(http.get("/api/applications", () => HttpResponse.json({ ...table, rows })));
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><ApplicationsPage /></MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Page 1 of 2")).toBeVisible();
    expect(screen.getByText("Matching applications: 42 of 42")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Café Labs" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next application page" }));
    expect(screen.getByRole("link", { name: "Café Labs" })).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Sort by"), "status");
    await user.type(screen.getByLabelText("Company or role"), "engineer cafe");
    expect(screen.getByRole("link", { name: "Café Labs" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "Engineer 42" })).toBeVisible();
    expect(screen.getByText("Matching applications: 1 of 42")).toBeVisible();
    expect(screen.getByRole("cell", { name: "Engineer 42" }).closest("tbody")?.querySelector('th[scope="rowgroup"]')).toHaveTextContent("Offer");
    expect(screen.queryByRole("columnheader", { name: "Status" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Company or role"), " nowhere");
    expect(screen.getByText("No applications match these filters.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByLabelText("Company or role")).toHaveFocus();
    expect(screen.getByText("Page 1 of 2")).toBeVisible();
  });

  it("uses context-aware Chinese labels for sorting and status filters", async () => {
    await changeLanguage("zh-CN");
    renderPage();

    const sort = await screen.findByLabelText("排序方式");
    expect(sort).toHaveValue("newest");
    expect(screen.getByRole("option", { name: "最新动态" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "公司名称 A–Z" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "按申请状态分组" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "面试中" })).toBeInTheDocument();
    expect(screen.getByText("符合条件的申请：1 条，共 1 条")).toBeInTheDocument();
  });

  it("compares two selected roles using the deterministic evidence endpoint", async () => {
    await changeLanguage("en");
    const rows = [
      table.rows[0],
      { ...table.rows[0], jobId: 43, company: "Globex", title: "Staff Engineer", fitScore: null },
    ];
    server.use(
      http.get("/api/applications", () => HttpResponse.json({ ...table, rows })),
      http.post("/api/jobs/company-intelligence-comparisons", async ({ request }) => {
        expect(await request.json()).toEqual({ jobIds: [42, 43] });
        return HttpResponse.json({
          items: [
            {
              jobId: 42,
              company: "Acme",
              title: "Senior SWE",
              fitScore: 82,
              applicationStatus: "interview",
              companyEvidence: {
                state: "ready",
                retrievedAt: "2026-08-30T12:00:00Z",
                isStale: false,
                researchDepth: "deep",
                sourceCount: 4,
                strongestVerification: "corroborated",
              },
              h1BStatus: "matched",
              offerTotal: null,
              offerCurrency: null,
            },
            {
              jobId: 43,
              company: "Globex",
              title: "Staff Engineer",
              fitScore: null,
              applicationStatus: "interview",
              companyEvidence: { state: "not_researched" },
              h1BStatus: null,
              offerTotal: 210000,
              offerCurrency: "USD",
            },
          ],
        });
      }),
    );
    const user = userEvent.setup();
    const { container } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><ApplicationsPage /></MemoryRouter>
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole("checkbox", { name: /select acme/i }));
    await user.click(screen.getByRole("checkbox", { name: /select globex/i }));
    await user.click(screen.getByRole("button", { name: "Compare selected" }));

    expect(await screen.findByRole("heading", { name: "Role comparison" })).toBeInTheDocument();
    expect(screen.getByText("deep · 4 sources · corroborated · current")).toBeInTheDocument();
    expect(screen.getByText("Not researched")).toBeInTheDocument();
    expect(screen.getByText("Historical filing match")).toBeInTheDocument();
    expect(screen.getByText("210,000 USD")).toBeInTheDocument();
    expect((await axe(container)).violations).toEqual([]);

    await changeLanguage("zh-CN");
    expect(await screen.findByText("深度 · 4 个来源 · 多来源印证 · 当前有效")).toBeInTheDocument();
    expect(screen.getByText("找到历史申报记录")).toBeInTheDocument();
  });

  it("does not allow terminal applications to be selected for comparison", async () => {
    await changeLanguage("en");
    const rows = [
      table.rows[0],
      {
        ...table.rows[0],
        jobId: 43,
        company: "Globex",
        title: "Closed role",
        status: "rejected",
      },
    ];
    server.use(http.get("/api/applications", () => HttpResponse.json({ ...table, rows })));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><ApplicationsPage /></MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("checkbox", { name: /globex closed role is closed/i })).toBeDisabled();
  });

  it("drops a selected role when a refresh closes it", async () => {
    await changeLanguage("en");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const rows = [table.rows[0], { ...table.rows[0], jobId: 43, company: "Globex" }];
    server.use(http.get("/api/applications", () => HttpResponse.json({ ...table, rows })));
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter><ApplicationsPage /></MemoryRouter>
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole("checkbox", { name: /select acme/i }));
    await user.click(screen.getByRole("checkbox", { name: /select globex/i }));
    expect(screen.getByRole("button", { name: "Compare selected" })).toBeEnabled();
    act(() => client.setQueryData(["applications"], { ...table, rows: [rows[0], { ...rows[1], status: "rejected" }] }));

    const closed = await screen.findByRole("checkbox", { name: /globex .* closed/i });
    expect(closed).toBeDisabled();
    expect(closed).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Compare selected" })).toBeDisabled();
  });
});
