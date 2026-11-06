import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type SetupProvider = components["schemas"]["SetupProviderOut"];
export type SetupProviderUpdate = components["schemas"]["SetupProviderUpdate"];

const queryKey = ["setup-provider"];

export function useSetupProvider() {
  return useQuery({
    queryKey,
    queryFn: () => unwrap(api.GET("/api/setup/provider")),
  });
}

export function useSaveSetupProvider() {
  const client = useQueryClient();
  return useMutation({
    gcTime: 0,
    mutationFn: (body: SetupProviderUpdate) => unwrap(api.PUT("/api/setup/provider", { body })),
    onSuccess: () => {
      // The write is complete. Refresh dependent views without delaying the next step.
      void Promise.all([
        client.invalidateQueries({ queryKey }),
        client.invalidateQueries({ queryKey: ["setup-status"] }),
        client.invalidateQueries({ queryKey: ["secrets"] }),
        client.invalidateQueries({ queryKey: ["config", "/api/config/models"] }),
        client.invalidateQueries({ queryKey: ["model-catalog"] }),
      ]);
    },
  });
}
