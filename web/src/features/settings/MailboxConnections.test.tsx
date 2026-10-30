import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { changeLanguage } from "@/i18n";
import { useRunStore } from "@/lib/runs/store";
import { MailboxConnections } from "./MailboxConnections";

vi.mock("@/lib/runs/sse", () => ({ watchRun: vi.fn() }));

const providers = [
  { id: "microsoft", name: "Outlook / Microsoft 365", auth: "oauth", available: false },
  { id: "yahoo", name: "Yahoo Mail", auth: "password", available: true, imapHost: "imap.mail.yahoo.com", smtpHost: "smtp.mail.yahoo.com", smtpPort: 465, smtpSecurity: "tls", helpUrl: "https://help.yahoo.com/kb/SLN4075.html" },
  { id: "custom", name: "Custom IMAP / SMTP", auth: "password", available: true },
];

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><MailboxConnections /></MemoryRouter></QueryClientProvider>);
  return client;
}

beforeEach(() => {
  useRunStore.setState({ runs: {} });
  server.use(http.get("/api/mailboxes", () => HttpResponse.json({ providers, accounts: [] })));
});

describe("MailboxConnections", () => {
  it("fills provider settings, tests credentials, and clears passwords after saving", async () => {
    const user = userEvent.setup();
    let submitted: unknown;
    server.use(http.post("/api/mailboxes", async ({ request }) => {
      submitted = await request.json();
      return HttpResponse.json({ id: "one", provider: "yahoo", email: "me@yahoo.com", folder: "INBOX", smtpConfigured: false });
    }));
    const client = mount();
    expect(await screen.findByRole("button", { name: "Connect Outlook / Microsoft 365" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Add email account" }));
    await user.selectOptions(screen.getByLabelText("Email provider"), "yahoo");
    expect(screen.getByLabelText("Server hostname")).toHaveValue("imap.mail.yahoo.com");
    await user.type(screen.getByLabelText("Mailbox email address"), "me@yahoo.com");
    expect(screen.getByLabelText("Username")).toHaveValue("me@yahoo.com");
    await user.type(screen.getByLabelText("App password"), "app-secret");
    expect(screen.getByLabelText("App password")).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Test & connect" }));
    await waitFor(() => expect(submitted).toEqual({
      provider: "yahoo", email: "me@yahoo.com", folder: "INBOX",
      imap: { host: "imap.mail.yahoo.com", port: 993, security: "tls", username: "me@yahoo.com", password: "app-secret" }, smtp: null,
    }));
    await waitFor(() => expect(screen.queryByLabelText("App password")).not.toBeInTheDocument());
    expect(JSON.stringify(client.getMutationCache().getAll().map((mutation) => mutation.state))).not.toContain("app-secret");
    expect(screen.getByRole("button", { name: "Add email account" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Add email account" }));
    expect(screen.getByLabelText("App password")).toHaveValue("");
  });

  it("keeps SMTP optional and supports separate credentials and STARTTLS", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", { name: "Add email account" }));
    await user.click(screen.getByRole("checkbox", { name: "Outgoing server (SMTP, optional)" }));
    const smtp = screen.getByRole("group", { name: "Outgoing server (SMTP, optional)" });
    await user.selectOptions(within(smtp).getByLabelText("Connection security"), "starttls");
    expect(within(smtp).getByLabelText("Port")).toHaveValue(587);
    expect(within(smtp).getByLabelText("App password")).toHaveValue("");
    expect(screen.getByText(/SMTP cannot retrieve emails/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add email account" })).toHaveFocus();
  });

  it("preserves the form and shows a safe server error when verification fails", async () => {
    const user = userEvent.setup();
    server.use(http.post("/api/mailboxes", () => HttpResponse.json({ error: { code: "MAILBOX_ERROR", message: "IMAP access failed." } }, { status: 503 })));
    mount();
    await user.click(await screen.findByRole("button", { name: "Add email account" }));
    await user.selectOptions(screen.getByLabelText("Email provider"), "yahoo");
    await user.type(screen.getByLabelText("Mailbox email address"), "me@yahoo.com");
    await user.type(screen.getByLabelText("App password"), "app-secret");
    await user.click(screen.getByRole("button", { name: "Test & connect" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("IMAP access failed.");
    expect(screen.getByRole("alert")).toHaveFocus();
    expect(screen.getByLabelText("Mailbox email address")).toHaveValue("me@yahoo.com");
  });

  it("focuses a safe error summary and links errors to their fields", async () => {
    const user = userEvent.setup();
    server.use(http.post("/api/mailboxes", () => HttpResponse.json({ error: {
      code: "MAILBOX_CREDENTIALS", message: "IMAP sign-in failed.",
      details: [{ loc: ["body", "imap", "password"], type: "MAILBOX_CREDENTIALS" }],
    } }, { status: 422 })));
    const client = mount();
    await user.click(await screen.findByRole("button", { name: "Add email account" }));
    expect(screen.getByLabelText("Email provider")).toHaveFocus();
    await user.selectOptions(screen.getByLabelText("Email provider"), "yahoo");
    await user.type(screen.getByLabelText("Mailbox email address"), "me@yahoo.com");
    await user.type(screen.getByLabelText("App password"), "app-secret");
    await user.click(screen.getByRole("button", { name: "Test & connect" }));
    expect(await screen.findByRole("alert")).toHaveFocus();
    expect(screen.getByLabelText("App password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("App password")).toHaveAccessibleDescription("Check this setting before trying again.");
    await user.click(screen.getByRole("link", { name: "Incoming mail (IMAP) · App password" }));
    expect(screen.getByLabelText("App password")).toHaveFocus();
    expect(screen.getByLabelText("App password")).toHaveValue("app-secret");
    expect(JSON.stringify(client.getMutationCache().getAll().map((mutation) => mutation.state))).not.toContain("app-secret");
  });

  it("keeps custom ports when changing security and supports password managers", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", { name: "Add email account" }));
    await user.clear(screen.getByLabelText("Port"));
    await user.type(screen.getByLabelText("Port"), "9993");
    await user.selectOptions(screen.getByLabelText("Connection security"), "starttls");
    expect(screen.getByLabelText("Port")).toHaveValue(9993);
    expect(screen.getByLabelText("App password")).toHaveAttribute("autocomplete", "section-imap current-password");
  });

  it("shows the actual syncing account and allows editing while sync is running", async () => {
    const user = userEvent.setup();
    server.use(http.get("/api/mailboxes", () => HttpResponse.json({ providers, accounts: [
      { id: "one", provider: "yahoo", email: "one@yahoo.com", folder: "INBOX" },
      { id: "two", provider: "yahoo", email: "two@yahoo.com", folder: "INBOX" },
    ] })));
    useRunStore.getState().upsert({ runId: "sync", kind: "mailboxSync", status: "running", percent: 0, phase: "", current: 0, total: 0, etaText: null, meta: { accountId: "one" } });
    mount();
    expect(await screen.findByRole("button", { name: "Syncing…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Sync & analyze" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Add email account" }));
    await user.type(screen.getByLabelText("Mailbox email address"), "new@example.com");
    expect(screen.getByLabelText("Mailbox email address")).toHaveValue("new@example.com");
    expect(screen.getByRole("button", { name: "Test & connect" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("An email operation is running.");
  });

  it("disconnects the selected account", async () => {
    const user = userEvent.setup();
    let removed = false;
    server.use(
      http.get("/api/mailboxes", () => HttpResponse.json({ providers, accounts: removed ? [] : [{ id: "account", provider: "yahoo", email: "me@yahoo.com", folder: "INBOX" }] })),
      http.delete("/api/mailboxes/account", () => { removed = true; return new HttpResponse(null, { status: 204 }); }),
    );
    mount();
    expect(await screen.findByText("me@yahoo.com")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(screen.queryByText("me@yahoo.com")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Add email account" })).toHaveFocus();
  });

  it("renders the connection form in Chinese", async () => {
    await changeLanguage("zh-CN");
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", { name: "添加邮箱账户" }));
    expect(screen.getByLabelText("应用专用密码")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "测试并连接" })).toBeInTheDocument();
  });
});
