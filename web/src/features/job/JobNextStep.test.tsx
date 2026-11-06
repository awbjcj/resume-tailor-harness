import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { useRunStore } from "@/lib/runs/store";
import { JobNextStep } from "./JobNextStep";

beforeEach(() => {
  useRunStore.setState({ runs: {} });
  server.use(http.get("/api/setup/status", () => HttpResponse.json({ secrets: { anyLlmKey: true }, profile: { factsBuiltAt: "today" } })));
});

describe("Job next step", () => {
  it("renders the chosen older resume directly and keeps a failure actionable", async () => {
    let renderedId: string | undefined;
    server.use(http.post("/api/resume-versions/:version_id/render", ({ params }) => {
      renderedId = String(params.version_id);
      return HttpResponse.json({ error: { code: "RENDER_FAILED", message: "Please retry rendering" } }, { status: 500 });
    }));
    const onTab = vi.fn();
    render(<MemoryRouter><JobNextStep job={{ id: 17, nextStep: { jobId: 17, kind: "render", href: "/pipeline?job=17&tab=resumes", resumeVersionId: 3 } }} onTab={onTab} /></MemoryRouter>, { wrapper: withQueryClient });
    await userEvent.click(screen.getByRole("button", { name: "Render PDF" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please retry rendering");
    expect(renderedId).toBe("3");
    expect(onTab).toHaveBeenCalledWith("resumes");
    expect(screen.getByRole("button", { name: "Render PDF" })).toBeEnabled();
  });

  it("keeps missing prerequisites attached to this Job", async () => {
    server.use(http.get("/api/setup/status", () => HttpResponse.json({ secrets: { anyLlmKey: true, modelTiersReady: false }, profile: { factsBuiltAt: "today" } })));
    render(<MemoryRouter><JobNextStep job={{ id: 17, nextStep: { jobId: 17, kind: "tailor", href: "/pipeline?job=17&tab=resumes" } }} onTab={() => {}} /></MemoryRouter>, { wrapper: withQueryClient });
    const link = await screen.findByRole("link", { name: "Continue setup" });
    expect(new URL(link.getAttribute("href")!, "https://example.test").searchParams.get("returnTo")).toBe("/pipeline?job=17&tab=resumes");
  });

  it("recognizes a bulk run already working on this Job", async () => {
    useRunStore.getState().upsert({ runId: "bulk", kind: "tailor", status: "running", percent: 2, phase: "", current: 0, total: 1, etaText: null, meta: { jobIds: [17] } });
    render(<MemoryRouter><JobNextStep job={{ id: 17, nextStep: { jobId: 17, kind: "tailor", href: "/pipeline?job=17&tab=resumes" } }} onTab={() => {}} /></MemoryRouter>, { wrapper: withQueryClient });
    await waitFor(() => expect(screen.getByRole("button", { name: "Work is in progress" })).toBeDisabled());
  });

  it("prevents a second paid launch while the first request is still pending", async () => {
    let launches = 0;
    let rejectLaunch: ((value: Response) => void) | undefined;
    server.use(http.post("/api/tailor", () => {
      launches++;
      return new Promise<Response>((resolve) => { rejectLaunch = resolve; });
    }));
    render(<MemoryRouter><JobNextStep job={{ id: 17, nextStep: { jobId: 17, kind: "tailor", href: "/pipeline?job=17&tab=resumes" } }} onTab={() => {}} /></MemoryRouter>, { wrapper: withQueryClient });
    await userEvent.dblClick(await screen.findByRole("button", { name: "Tailor resume" }));
    await waitFor(() => expect(launches).toBe(1));
    expect(screen.getByRole("button", { name: "Work is in progress" })).toBeDisabled();
    rejectLaunch?.(HttpResponse.json({ error: { code: "TEST_STOP", message: "Retry allowed" } }, { status: 409 }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Tailor resume" })).toBeEnabled());
  });
});
