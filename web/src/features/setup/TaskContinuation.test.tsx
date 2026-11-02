import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { LoginPage } from "@/features/auth/LoginPage";
import { AuthGate } from "@/features/auth/AuthGate";
import { SetupGate } from "./SetupGate";
import { DocumentsStep } from "./steps/DocumentsStep";
import { firstIncompleteStep } from "./setup-flow";

vi.mock("@/features/settings/forms/DocumentManager", () => ({ DocumentManager: () => <div>Documents</div> }));
vi.mock("@/features/auth/GoogleButton", () => ({ GoogleButton: () => null }));

const status = { complete: false, secrets: { anyLlmKey: true, anthropicKey: true }, profile: { hasResume: true, canRebuild: true, factsBuiltAt: "2026-11-02", documentCount: 1, githubUsername: null, freshness: "current" as const, pendingSourceCount: 0 }, search: { configured: false }, sources: { enabledCount: 0 } };
beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });

describe("task-aware setup", () => {
  it("lets an imported Job open without discovery settings", async () => {
    server.use(http.get("/api/setup/status", () => HttpResponse.json(status)));
    render(<MemoryRouter initialEntries={["/pipeline?job=17&tab=resumes"]}><SetupGate><div>Chosen job</div></SetupGate></MemoryRouter>, { wrapper: withQueryClient });
    expect(await screen.findByText("Chosen job")).toBeInTheDocument();
    expect(firstIncompleteStep(status, "/pipeline?job=17")).toBe("finish");
    expect(firstIncompleteStep(status)).toBe("search");
  });

  it("keeps the Job and tab through sign in", async () => {
    server.use(
      http.get("/api/auth/me", () => HttpResponse.json({ authRequired: true, username: null })),
      http.post("/api/auth/login", () => HttpResponse.json({ authRequired: true, username: "user", needsEmail: false })),
    );
    render(<MemoryRouter initialEntries={["/pipeline?job=17&tab=resumes"]}><Routes>
      <Route path="/pipeline" element={<AuthGate><div>Original job</div></AuthGate>} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<div>Dashboard</div>} />
    </Routes></MemoryRouter>, { wrapper: withQueryClient });
    await userEvent.type(await screen.findByLabelText("Email"), "user@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Original job")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("waits for save and retains the draft when persistence fails", async () => {
    let finish: ((response: Response) => void) | undefined;
    let attempts = 0;
    server.use(
      http.get("/api/config/profile", () => HttpResponse.json({ githubUsername: "original", githubRepoAllow: [], githubRepoDeny: [], githubRepoLimit: 10, githubRepoBranches: {} })),
      http.put("/api/config/profile", () => { attempts++; return new Promise<Response>((resolve) => { finish = resolve; }); }),
    );
    render(<MemoryRouter initialEntries={["/setup/documents?returnTo=%2Fpipeline%3Fjob%3D17"]}><Routes>
      <Route path="/setup/documents" element={<DocumentsStep />} />
      <Route path="/setup/finish" element={<div>Ready to return</div>} />
    </Routes></MemoryRouter>, { wrapper: withQueryClient });
    const input = await screen.findByLabelText("GitHub username");
    await userEvent.clear(input);
    await userEvent.type(input, "kept-draft");
    await userEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => expect(attempts).toBe(1));
    expect(screen.queryByText("Ready to return")).not.toBeInTheDocument();
    finish?.(HttpResponse.json({ error: { code: "SAVE_FAILED", message: "Please retry" } }, { status: 500 }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save & continue" })).toBeEnabled());
    expect(input).toHaveValue("kept-draft");
    await userEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => expect(attempts).toBe(2));
    finish?.(HttpResponse.json({ githubUsername: "kept-draft" }));
    expect(await screen.findByText("Ready to return")).toBeInTheDocument();
  });
});
