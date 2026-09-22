import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/server";
import type { components } from "@/lib/api/schema";
import { MemberSubscriptionForm } from "./MemberSubscriptionForm";

const account: components["schemas"]["QuotaAccountOut"] = {
  userId: "alice0000000", username: "alice", disabled: false, tierId: "FREE",
  allowanceMicros: 1000000, overrideMicros: null, spentMicros: 0,
  recurringRemainingMicros: 1000000, creditBalanceMicros: 0, remainingMicros: 1000000,
  overageMicros: 0, periodStart: "2026-09-01T00:00:00Z", periodEnd: "2026-09-08T00:00:00Z",
  status: "ACTIVE", sharedCostMicros: 0, byokCostMicros: 0, totalTokens: 0,
};
const tiers: components["schemas"]["QuotaTierOut"][] = [
  { id: "SUBSCRIBER", name: "Subscriber", cycleUnit: "MONTH", cycleCount: 1,
    allowanceMicros: 20000000, isDefault: false, archivedAt: null, memberCount: 0, spendMicros: 0 },
];

describe("MemberSubscriptionForm", () => {
  it("keeps the operation identity on retry and submits the selected finite term", async () => {
    const requests: Record<string, unknown>[] = [];
    server.use(http.post("/api/admin/quota-accounts/:userId/subscription", async ({ request }) => {
      requests.push(await request.json() as Record<string, unknown>);
      if (requests.length === 1) return HttpResponse.json({ error: { code: "UNAVAILABLE", message: "Please retry" } }, { status: 503 });
      return HttpResponse.json({ status: "ACTIVE" });
    }));
    const saved = vi.fn();
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
      <MemberSubscriptionForm account={account} tiers={tiers} onSaved={saved} />
    </QueryClientProvider>);
    await user.selectOptions(screen.getByLabelText("Subscription plan"), "SUBSCRIBER");
    await user.clear(screen.getByLabelText("Plan cycles (1–52)"));
    await user.type(screen.getByLabelText("Plan cycles (1–52)"), "2");
    await user.type(screen.getByLabelText("Subscription change reason"), "Invoice 123 paid");
    await user.click(screen.getByRole("button", { name: "Apply subscription change" }));
    expect(await screen.findByText("Please retry")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply subscription change" }));
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    expect(requests[0]).toEqual(requests[1]);
    expect(requests[0]).toMatchObject({ action: "ACTIVATE", cycles: 2, tierId: "SUBSCRIBER", reason: "Invoice 123 paid" });
  });
});
