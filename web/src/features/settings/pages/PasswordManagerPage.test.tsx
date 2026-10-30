import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { changeLanguage } from "@/i18n";
import { PasswordManagerPage } from "./PasswordManagerPage";

const account = { id: "one", company: "Acme", origin: "https://careers.example.com", username: "user@example.com", status: "active", revision: 1, createdAt: "2026-10-29", updatedAt: "2026-10-29", lastUsedAt: null };

describe("PasswordManagerPage", () => {
  it("saves a login without putting its password in the query cache or leaving it in the form", async () => {
    let accounts: typeof account[] = [];
    let received: Record<string, unknown> = {};
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    server.use(
      http.get("/api/application-accounts", () => HttpResponse.json({ configured: true, autoRegister: false, revision: 0, accounts })),
      http.post("/api/application-accounts", async ({ request }) => { received = await request.json() as Record<string, unknown>; accounts = [account]; return HttpResponse.json(account); }),
    );
    render(<QueryClientProvider client={qc}><PasswordManagerPage /></QueryClientProvider>);
    fireEvent.change(await screen.findByLabelText("Employer"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("HTTPS login URL"), { target: { value: account.origin + "/login" } });
    fireEvent.change(screen.getByLabelText("Email or username"), { target: { value: account.username } });
    fireEvent.change(screen.getByLabelText("Password", { exact: true }), { target: { value: "Sensitive-test-secret!" } });
    fireEvent.click(screen.getByRole("button", { name: "Save account" }));
    await screen.findByText("Ready to sign in");
    expect(received.password).toBe("Sensitive-test-secret!");
    expect(received.userConfirmed).toBe(true);
    expect(screen.getByLabelText("Password", { exact: true })).toHaveValue("");
    expect(JSON.stringify(qc.getQueryCache().getAll().map((q) => q.state))).not.toContain("Sensitive-test-secret!");
    expect(qc.getMutationCache().getAll()).toHaveLength(0);
    expect(document.body.textContent).not.toContain("Sensitive-test-secret!");
  });

  it("requires explicit deletion and sends the account revision", async () => {
    let deleted = false;
    server.use(
      http.get("/api/application-accounts", () => HttpResponse.json({ configured: true, autoRegister: false, revision: 1, accounts: deleted ? [] : [account] })),
      http.delete("/api/application-accounts/one", ({ request }) => { expect(new URL(request.url).searchParams.get("revision")).toBe("1"); deleted = true; return new HttpResponse(null, { status: 204 }); }),
    );
    render(<PasswordManagerPage />, { wrapper: withQueryClient });
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(deleted).toBe(false);
    expect(screen.getByText(/This does not delete your account/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove saved login" }));
    await waitFor(() => expect(deleted).toBe(true));
    await screen.findByText(/No saved employer logins/);
  });

  it("enables registration explicitly and localizes the controls", async () => {
    const user = userEvent.setup();
    let enabled = false;
    server.use(
      http.get("/api/application-accounts", () => HttpResponse.json({ configured: true, autoRegister: enabled, revision: 0, accounts: [] })),
      http.patch("/api/application-accounts/policy", async ({ request }) => { expect(await request.json()).toEqual({ autoRegister: true, revision: 0, userConfirmed: true }); enabled = true; return HttpResponse.json({ configured: true, autoRegister: enabled, revision: 1, accounts: [] }); }),
    );
    render(<PasswordManagerPage />, { wrapper: withQueryClient });
    const control = await screen.findByRole("switch", { name: "Create accounts during applications" });
    expect(control).not.toBeChecked();
    await user.click(control);
    await waitFor(() => expect(control).toBeChecked());
    await act(() => changeLanguage("zh-CN"));
    expect(screen.getByRole("heading", { name: "密码管理器" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "申请时自动创建账号" })).toBeInTheDocument();
    await act(() => changeLanguage("en"));
  });

  it("shows configuration guidance and prevents writes when unavailable", async () => {
    server.use(http.get("/api/application-accounts", () => HttpResponse.json({ configured: false, accounts: [] })));
    render(<PasswordManagerPage />, { wrapper: withQueryClient });
    await screen.findByText(/password manager is not configured/);
    expect(screen.queryByRole("button", { name: "Save account" })).not.toBeInTheDocument();
  });

  it("clears a failed password write and does not echo the server's error body", async () => {
    server.use(
      http.get("/api/application-accounts", () => HttpResponse.json({ configured: true, autoRegister: false, revision: 1, accounts: [account] })),
      http.patch("/api/application-accounts/one", () => HttpResponse.json({ error: { code: "ACCOUNT_STALE", message: "secret-should-not-appear" } }, { status: 409 })),
    );
    render(<PasswordManagerPage />, { wrapper: withQueryClient });
    fireEvent.click(await screen.findByRole("button", { name: "Update password" }));
    const password = screen.getByLabelText("Current password on the employer site");
    fireEvent.change(password, { target: { value: "secret-should-not-appear" } });
    fireEvent.click(screen.getByRole("button", { name: "Save password" }));
    await screen.findByText(/This account changed elsewhere/);
    await waitFor(() => expect(password).toHaveValue(""));
    expect(document.body.textContent).not.toContain("secret-should-not-appear");
  });

  it("refreshes a conflicted edit, focuses its error, and allows an explicit retry", async () => {
    let revision = 1;
    const revisions: number[] = [];
    server.use(
      http.get("/api/application-accounts", () => HttpResponse.json({ configured: true, autoRegister: false, revision, accounts: [{ ...account, revision }] })),
      http.patch("/api/application-accounts/one", async ({ request }) => {
        const body = await request.json() as { revision: number };
        revisions.push(body.revision);
        if (revisions.length === 1) {
          revision = 2;
          return HttpResponse.json({ error: { code: "ACCOUNT_STALE" } }, { status: 409 });
        }
        expect(body.revision).toBe(2);
        return HttpResponse.json({ ...account, revision: 3 });
      }),
    );
    render(<PasswordManagerPage />, { wrapper: withQueryClient });
    fireEvent.click(await screen.findByRole("button", { name: "Update password" }));
    const password = screen.getByLabelText("Current password on the employer site");
    expect(password).toHaveFocus();
    fireEvent.change(password, { target: { value: "first-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Save password" }));
    await screen.findByText(/This account changed elsewhere/);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveFocus());
    expect(password).toHaveValue("");
    fireEvent.change(password, { target: { value: "replacement-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Save password" }));
    await screen.findByRole("button", { name: "Save account" });
    expect(revisions).toEqual([1, 2]);
  });

  it("returns keyboard focus after cancelling edit and removal, and toggles only the entered password", async () => {
    const user = userEvent.setup();
    server.use(http.get("/api/application-accounts", () => HttpResponse.json({ configured: true, autoRegister: false, revision: 1, accounts: [account] })));
    render(<PasswordManagerPage />, { wrapper: withQueryClient });
    const edit = await screen.findByRole("button", { name: "Update password" });
    await user.click(edit);
    const password = screen.getByLabelText("Current password on the employer site");
    await user.type(password, "entered-password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(edit).toHaveFocus();
    expect(screen.getByLabelText("Password", { exact: true })).toHaveValue("");
    const remove = screen.getByRole("button", { name: "Remove" });
    await user.click(remove);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(remove).toHaveFocus();
    expect(remove).toHaveAttribute("aria-expanded", "false");
  });

  it("connects server validation to the invalid field without displaying raw error text", async () => {
    server.use(
      http.get("/api/application-accounts", () => HttpResponse.json({ configured: true, autoRegister: false, revision: 0, accounts: [] })),
      http.post("/api/application-accounts", () => HttpResponse.json({ error: { code: "INVALID_LOGIN_URL", message: "private-server-value" } }, { status: 422 })),
    );
    render(<PasswordManagerPage />, { wrapper: withQueryClient });
    fireEvent.change(await screen.findByLabelText("Employer"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("HTTPS login URL"), { target: { value: "https://careers.example.com:444/login" } });
    fireEvent.change(screen.getByLabelText("Email or username"), { target: { value: "user" } });
    fireEvent.change(screen.getByLabelText("Password", { exact: true }), { target: { value: "test-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Save account" }));
    const link = await screen.findByRole("link", { name: /Use a valid HTTPS/ });
    expect(link).toHaveAttribute("href", "#account-url");
    expect(screen.getByLabelText("HTTPS login URL")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("HTTPS login URL")).toHaveAccessibleDescription(/Use a valid HTTPS/);
    expect(document.body.textContent).not.toContain("private-server-value");
  });
});
