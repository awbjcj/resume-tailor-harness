import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { useLaunchRun } from "@/features/runs/use-launch-run";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useRunStore } from "@/lib/runs/store";

export type SuggestionEnvelope = components["schemas"]["SuggestionEnvelope"];
export type SuggestionKind = "skill" | "domain";

export function suggestionQueryKey(kind: SuggestionKind, key: string): string {
  return `suggestion:${kind}:${key}`;
}

export function useSuggestion(
  kind: SuggestionKind,
  key: string | null,
  enabled: boolean,
) {
  const queryKey = suggestionQueryKey(kind, key ?? "");
  return useQuery({
    queryKey: [queryKey],
    enabled: enabled && Boolean(key),
    queryFn: (): Promise<SuggestionEnvelope> =>
      unwrap(
        api.GET("/api/suggestions", {
          params: { query: { kind, key: key ?? "" } },
        }),
      ) as Promise<SuggestionEnvelope>,
  });
}

export function useGenerateSuggestion() {
  const { launch } = useLaunchRun();
  const pending = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const running = useRunStore((state) =>
    Object.values(state.runs).some(
      (run) =>
        run.kind === "suggestion" &&
        (run.status === "queued" || run.status === "running" || run.status === "cancelling"),
    ),
  );
  const generate = async (kind: SuggestionKind, key: string, expectedRoadmapId?: number) => {
    if (pending.current) return false;
    pending.current = true;
    setSubmitting(true);
    try {
      return await launch(
        "suggestion",
        () =>
          unwrap(
            api.POST("/api/suggestions/generate", {
              body: { kind, key, expectedRoadmapId },
            }),
          ),
        [suggestionQueryKey(kind, key)],
      );
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  };

  return { generate, generating: submitting || running };
}
