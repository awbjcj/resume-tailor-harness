import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type ApplicationsTableData = components["schemas"]["PivotTableOut"];

export function useApplications(enabled = true) {
  return useQuery({
    queryKey: ["applications"],
    enabled,
    queryFn: (): Promise<ApplicationsTableData> => unwrap(api.GET("/api/applications")),
  });
}
