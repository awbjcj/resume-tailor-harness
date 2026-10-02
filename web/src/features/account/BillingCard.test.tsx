import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { server } from "@/test/server";
import { changeLanguage } from "@/i18n";
import { BillingCard } from "./BillingCard";
import { billingRedirect } from "./billing-redirect";

vi.mock("./billing-redirect", () => ({ billingRedirect: vi.fn() }));

const offers = [
  { priceId: "price_credit", name: "Credit top-up", mode: "payment", amountCents: 1000, currency: "usd", creditMicros: 10_000_000 },
  { priceId: "price_plan", name: "Subscriber", mode: "subscription", amountCents: 2000, currency: "usd", tierId: "SUBSCRIBER", allowanceMicros: 20_000_000, interval: "month", intervalCount: 1 },
];
function mount(path = "/account") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><BillingCard /></MemoryRouter></QueryClientProvider>);
  return { ...view, client, invalidate };
}
beforeEach(() => {
  vi.clearAllMocks();
  server.use(http.get("/api/account/billing", () => HttpResponse.json({ enabled: true, offers, portalAvailable: false })));
});

describe("BillingCard", () => {
  it("shows priced credit and recurring allowance purchases accessibly", async () => {
    const { container } = mount();
    expect(await screen.findByRole("button", { name: /^Add credit for/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^Subscribe to/ })).toBeEnabled();
    expect(screen.getByText("every month")).toBeInTheDocument();
    expect(screen.getByText(/Subscriptions renew automatically/)).toBeInTheDocument();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("hides billing when the deployment disables it", async () => {
    server.use(http.get("/api/account/billing", () => HttpResponse.json({ enabled: false })));
    const { container } = mount();
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("reuses a purchase key after an ambiguous failure and redirects only on success", async () => {
    const bodies: unknown[] = [];
    server.use(http.post("/api/account/billing/checkout", async ({ request }) => {
      bodies.push(await request.json());
      return bodies.length === 1 ? HttpResponse.json({ error: { code: "BILLING_PROVIDER_UNAVAILABLE", message: "Please retry" } }, { status: 502 }) : HttpResponse.json({ url: "https://checkout.stripe.com/test", checkoutId: "cs_test" });
    }));
    mount();
    const button = await screen.findByRole("button", { name: /^Add credit for/ });
    await userEvent.click(button);
    expect(await screen.findByText("Please retry")).toBeInTheDocument();
    expect(billingRedirect).not.toHaveBeenCalled();
    await userEvent.click(button);
    await waitFor(() => expect(billingRedirect).toHaveBeenCalledWith("https://checkout.stripe.com/test"));
    expect(bodies[0]).toEqual(bodies[1]);
    expect(bodies[0]).toMatchObject({ priceId: "price_credit" });
  });

  it("does not treat a return URL as payment confirmation", async () => {
    server.use(http.get("/api/account/billing/checkout/:session", () => HttpResponse.json({ status: "open" })));
    const { invalidate } = mount("/account?billing=success&session_id=cs_test");
    expect(await screen.findByText("Waiting for payment confirmation")).toBeInTheDocument();
    expect(screen.queryByText("Payment received")).not.toBeInTheDocument();
    expect(invalidate).not.toHaveBeenCalled();
    server.use(http.get("/api/account/billing/checkout/:session", () => HttpResponse.json({ status: "fulfilled" })));
    await userEvent.click(screen.getByRole("button", { name: "Refresh payment status" }));
    expect(await screen.findByText("Payment received")).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["account", "usage"] });
  });

  it("starts a new purchase only after the server confirms the previous checkout ended", async () => {
    const keys: string[] = [];
    server.use(http.post("/api/account/billing/checkout", async ({ request }) => {
      const body = await request.json() as { idempotencyKey: string };
      keys.push(body.idempotencyKey);
      return keys.length === 1 ? HttpResponse.json({ error: { code: "BILLING_CHECKOUT_ENDED", message: "Start a new purchase" } }, { status: 409 }) : HttpResponse.json({ url: "https://checkout.stripe.com/new", checkoutId: "cs_new" });
    }));
    mount();
    const button = await screen.findByRole("button", { name: /^Add credit for/ });
    await userEvent.click(button);
    expect(await screen.findByText("Start a new purchase")).toBeInTheDocument();
    await userEvent.click(button);
    await waitFor(() => expect(billingRedirect).toHaveBeenCalledWith("https://checkout.stripe.com/new"));
    expect(keys[0]).not.toBe(keys[1]);
  });

  it("routes existing subscribers to their portal and explains scheduled cancellation", async () => {
    server.use(
      http.get("/api/account/billing", () => HttpResponse.json({ enabled: true, offers, portalAvailable: true, subscription: { status: "active", cancelAtPeriodEnd: true, paidThrough: "2026-11-02T00:00:00Z" } })),
      http.post("/api/account/billing/portal", () => HttpResponse.json({ url: "https://billing.stripe.com/test" })),
    );
    mount();
    expect(await screen.findByRole("button", { name: "Subscription managed" })).toBeDisabled();
    expect(screen.getByText(/Cancels at the end of the paid term/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Add credit for/ })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Manage billing" }));
    await waitFor(() => expect(billingRedirect).toHaveBeenCalledWith("https://billing.stripe.com/test"));
  });

  it("translates the purchase flow into Simplified Chinese", async () => {
    await changeLanguage("zh-CN");
    mount();
    expect(await screen.findByRole("button", { name: /^充值并支付/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^订阅 / })).toBeInTheDocument();
    expect(screen.getByText("每 1 个月")).toBeInTheDocument();
  });
});
