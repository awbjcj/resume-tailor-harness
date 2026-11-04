import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { emptyFilterState } from "@/lib/filters/types";
import { server } from "@/test/server";
import { changeLanguage } from "@/i18n";

import { useBulkAction } from "./use-bulk-action";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useBulkAction", () => {
  it("sends filter for query scope and returns the result", async () => {
    let received: Record<string, unknown> | undefined;
    server.use(
      http.post("/api/jobs/bulk", async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ affected: 10, skipped: 1, reasons: { hasProgress: 1 } });
      }),
    );
    const filter = emptyFilterState();
    filter.source = new Set(["adzuna"]);
    filter.rejectReason = "sponsorship";
    const { result } = renderHook(() => useBulkAction("triage"), { wrapper });
    const res = await result.current.preview({
      action: "delete",
      selection: { mode: "query", ids: new Set<number>() },
      filter,
    });
    expect(received).toMatchObject({
      scope: "query",
      source: ["adzuna"],
      rejectReason: "sponsorship",
      dryRun: true,
    });
    expect(res.affected).toBe(10);
  });

  it("announces the result in Chinese without exposing the action identifier", async () => {
    await changeLanguage("zh-CN");
    const notice = vi.spyOn(toast, "success").mockImplementation(() => "toast-id");
    server.use(http.post("/api/jobs/bulk", () => HttpResponse.json({ affected: 2, skipped: 1, reasons: {} })));
    const { result } = renderHook(() => useBulkAction("pipeline"), { wrapper });
    await result.current.run({ action: "setStatus", selection: { mode: "ids", ids: new Set([1, 2]) }, filter: emptyFilterState(), status: "approved" });
    expect(notice).toHaveBeenCalledWith("已更新 2 个职位的状态 · 跳过 1 个");
    notice.mockRestore();
  });
});
