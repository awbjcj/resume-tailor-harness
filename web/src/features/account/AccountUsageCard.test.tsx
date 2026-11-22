import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { AccountUsageCard } from "./AccountUsageCard";

const adminUsage = {
  weightedTotal: 12_400,
  ownKeyWeightedTotal: 820,
  budget: 0,
  costs: {
    sharedQuotaCostMicros: 2_500_000,
    byokEstimatedCostMicros: 750_000,
    toolCostMicros: 0,
    unpricedCallCount: 0,
  },
  sharedTokens: { inputTokens: 800, outputTokens: 200, cacheReadTokens: 0, cacheWriteTokens: 0, reasoningTokens: 0, audioTokens: 0, totalTokens: 1_000 },
  byokTokens: { inputTokens: 300, outputTokens: 100, cacheReadTokens: 0, cacheWriteTokens: 0, reasoningTokens: 0, audioTokens: 0, totalTokens: 400 },
};

describe("AccountUsageCard", () => {
  it("shows recorded costs and tokens for a quota-exempt administrator", async () => {
    const { container } = render(<AccountUsageCard usage={adminUsage} isAdmin />);

    expect(screen.getByText("No usage ceiling")).toBeInTheDocument();
    expect(screen.getByText("Shared-key spend")).toBeInTheDocument();
    expect(screen.getByText("$2.50")).toBeInTheDocument();
    expect(screen.getByText("BYOK estimated spend")).toBeInTheDocument();
    expect(screen.getByText("$0.75")).toBeInTheDocument();
    expect(screen.getByText("1,000")).toBeInTheDocument();
    expect((await axe(container)).violations).toEqual([]);
  });

  it.each([
    ["ACTIVE", "正常"],
    ["EXHAUSTED", "已用尽"],
    ["OVERAGE", "超额"],
    ["SHADOW", "仅监测"],
    ["FUTURE_STATUS", "FUTURE_STATUS"],
  ])("localizes the %s quota status and unlimited balance", async (status, label) => {
    await changeLanguage("zh-CN");
    render(<AccountUsageCard isAdmin={false} usage={{
      ...adminUsage,
      quota: {
        allowanceOverrideMicros: null,
        creditBalanceMicros: 0,
        enforcementStatus: status,
        nextResetAt: "2026-12-01T00:00:00Z",
        overageMicros: 0,
        periodEnd: "2026-12-01T00:00:00Z",
        periodStart: "2026-11-01T00:00:00Z",
        recurringAllowanceMicros: null,
        remainingMicros: null,
        spendMicros: 0,
        tierId: "unlimited",
        tierName: "Unlimited plan",
      },
    }} />);

    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByText("无限额度")).toBeInTheDocument();
    expect(screen.getByText(/此账户没有个人额度上限/)).toBeInTheDocument();
  });
});
