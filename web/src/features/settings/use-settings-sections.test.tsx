import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { server } from "@/test/server";
import { useDraft } from "./use-draft";
import { useResetSection } from "./use-settings-sections";

it("does not restore pre-reset cached settings when refetch fails", async () => {
  server.use(http.post("/api/settings/sections/search/reset", () => HttpResponse.json({ id: "search", label: "Search" })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(["config", "search"], { n: 99 });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  const { result } = renderHook(() => {
    const query = useQuery<{ n: number }>({ queryKey: ["config", "search"], queryFn: async () => { throw new Error("refetch unavailable"); } });
    const draft = useDraft(query.data);
    const reset = useResetSection();
    return { draft, reset };
  }, { wrapper: Wrapper });
  expect(result.current.draft.draft).toEqual({ n: 99 });
  await act(async () => {
    await result.current.reset.mutateAsync({ sectionId: "search" }, { onSuccess: () => result.current.draft.setDraft(null) });
  });
  await waitFor(() => expect(result.current.draft.draft).toBeNull());
  expect(client.getQueryData(["config", "search"])).toBeUndefined();
  client.clear();
});
