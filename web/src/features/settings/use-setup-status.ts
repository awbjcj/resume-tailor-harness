import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { paths } from "@/lib/api/schema";

export type SetupStatus =
  paths["/api/setup/status"]["get"]["responses"][200]["content"]["application/json"];

export function setupModelsReady(status: SetupStatus) {
  return status.secrets.modelTiersReady ?? status.secrets.anyLlmKey;
}

export function useSetupStatus() {
  return useQuery({
    queryKey: ["setup-status"],
    queryFn: () => unwrap(api.GET("/api/setup/status", {} as never)) as Promise<SetupStatus>,
  });
}
