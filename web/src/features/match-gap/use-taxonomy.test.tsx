import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { MATCH_GAP_QUERY_KEY } from "./use-match-gap";
import { useMoveSkill, useRestoreSkills } from "./use-taxonomy";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

it("writes the mutation response directly into the match-gap cache", async () => {
  const fresh = { targetTotal: 1, marker: "fresh" };
  server.use(
    http.put("/api/taxonomy/skills/:token/domain", () =>
      HttpResponse.json(fresh),
    ),
  );
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  client.setQueryData(MATCH_GAP_QUERY_KEY, { targetTotal: 0, marker: "stale" });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useMoveSkill(), { wrapper });

  act(() => result.current.mutate({ token: "python", domainId: "backend" }));

  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(client.getQueryData(MATCH_GAP_QUERY_KEY)).toEqual(fresh);
});

it("restores a large non-skill list within the API's 500-entry limit", async () => {
  const batches: string[][] = [];
  server.use(
    http.post("/api/match-gap/restore-skills", async ({ request }) => {
      const { skillKeys } = (await request.json()) as { skillKeys: string[] };
      batches.push(skillKeys);
      return HttpResponse.json({
        restored: skillKeys.length,
        restoredSkills: skillKeys,
      });
    }),
  );
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useRestoreSkills(), { wrapper });
  act(() =>
    result.current.mutate(Array.from({ length: 706 }, (_, i) => `entry ${i}`)),
  );
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(batches.map((batch) => batch.length)).toEqual([500, 206]);
  expect(result.current.data?.restored).toBe(706);
});
