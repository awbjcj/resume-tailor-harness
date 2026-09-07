import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Draft = components["schemas"]["DraftOut"];
export type JobFacts = components["schemas"]["JobFacts-Input"];
export type BoardPlan = components["schemas"]["BoardPlan"];
export type CrawlLimits = components["schemas"]["CrawlLimits"];
export type ApprovalResult = components["schemas"]["ApprovalResultOut"];
export const defaultLimits: CrawlLimits = {
  listingPages: 10,
  detailPages: 50,
  elapsedSeconds: 300,
};

export function useScrapeDraft(id: string) {
  return useQuery({
    queryKey: ["scrape-draft", id],
    queryFn: () =>
      unwrap(
        api.GET("/api/scrape/drafts/{draft_id}", {
          params: { path: { draft_id: id } },
        }),
      ),
    enabled: Boolean(id),
  });
}

export function useScrapeSources() {
  return useQuery({
    queryKey: ["scrape-sources"],
    queryFn: () => unwrap(api.GET("/api/scrape/sources")),
  });
}
