import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type RunCompletionItem = components["schemas"]["RunCompletionOut"];
export const RUN_COMPLETIONS_KEY = ["run-completions"] as const;

export function useRunCompletions(surface: "operations" | "notifications" = "notifications") {
  return useQuery<RunCompletionItem[]>({
    queryKey: [...RUN_COMPLETIONS_KEY, surface],
    refetchInterval: 15_000,
    queryFn: () => unwrap(api.GET("/api/run-completions", { params: { query: { surface } } })),
  });
}

export function useMarkRunCompletionRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST("/api/run-completions/{completion_id}/read", {
          params: { path: { completion_id: id } },
        }),
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: RUN_COMPLETIONS_KEY }),
  });
}

export function useMarkAllRunCompletionsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/run-completions/read-all")),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: RUN_COMPLETIONS_KEY }),
  });
}


export function useClearOperationHistory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/run-completions")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: RUN_COMPLETIONS_KEY }),
  });
}
