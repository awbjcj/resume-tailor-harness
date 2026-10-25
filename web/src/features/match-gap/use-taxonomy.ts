import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { MATCH_GAP_QUERY_KEY } from "./use-match-gap";

type MatchGap = components["schemas"]["MatchGapOut"];
export type NewDomainInput = { label: string; category: string };

function useTaxonomyMutationMessage<V>(
  run: (variables: V) => Promise<MatchGap>,
  message: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (payload) => {
      queryClient.setQueryData(MATCH_GAP_QUERY_KEY, payload);
      toast.success(message);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * Restoring returns a small receipt rather than the whole graph, so this
 * invalidates the match-gap query instead of writing it directly.
 */
export function useRestoreSkills() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (skillKeys: string[]) => {
      const restoredSkills: string[] = [];
      for (let offset = 0; offset < skillKeys.length; offset += 500) {
        const result = await unwrap(
          api.POST("/api/match-gap/restore-skills", {
            body: { skillKeys: skillKeys.slice(offset, offset + 500) },
          }),
        );
        restoredSkills.push(...result.restoredSkills);
      }
      return { restored: restoredSkills.length, restoredSkills };
    },
    onSuccess: (result) => {
      toast.success(
        result.restored === 1
          ? "Skill restored"
          : `${result.restored} skills restored`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: MATCH_GAP_QUERY_KEY });
    },
  });
}

export function useDiscardSkills() {
  return useTaxonomyMutationMessage(
    (skillKeys: string[]) =>
      unwrap(
        api.POST("/api/taxonomy/discard-skills", {
          body: { skillKeys },
        }),
      ) as Promise<MatchGap>,
    "Selected entries discarded. You can restore them from discarded non-skills.",
  );
}

export function useMoveSkill() {
  return useTaxonomyMutationMessage(
    (variables: {
      token: string;
      domainId?: string;
      newDomain?: NewDomainInput;
    }) =>
      unwrap(
        api.PUT("/api/taxonomy/skills/{token}/domain", {
          params: { path: { token: variables.token } },
          body: {
            domainId: variables.domainId,
            newDomain: variables.newDomain,
          },
        }),
      ) as Promise<MatchGap>,
    "Skill moved",
  );
}
export function useAddSkill() {
  return useTaxonomyMutationMessage(
    (variables: {
      token: string;
      domainId?: string;
      newDomain?: NewDomainInput;
    }) =>
      unwrap(
        api.POST("/api/taxonomy/skills", { body: variables }),
      ) as Promise<MatchGap>,
    "Skill added",
  );
}
export function useRemoveSkill() {
  return useTaxonomyMutationMessage(
    (variables: { token: string }) =>
      unwrap(
        api.DELETE("/api/taxonomy/skills/{token}", {
          params: { path: { token: variables.token } },
        }),
      ) as Promise<MatchGap>,
    "Skill removed",
  );
}
export function useMergeSkills() {
  return useTaxonomyMutationMessage(
    (variables: { token: string; canonical: string }) =>
      unwrap(
        api.POST("/api/taxonomy/aliases", { body: variables }),
      ) as Promise<MatchGap>,
    "Skills merged",
  );
}
export function usePatchDomain() {
  return useTaxonomyMutationMessage(
    (variables: {
      domainId: string;
      body: { label?: string; category?: string };
    }) =>
      unwrap(
        api.PATCH("/api/taxonomy/domains/{domain_id}", {
          params: { path: { domain_id: variables.domainId } },
          body: variables.body,
        }),
      ) as Promise<MatchGap>,
    "Domain updated",
  );
}
export function useMergeDomains() {
  return useTaxonomyMutationMessage(
    (variables: { domainId: string; into: string }) =>
      unwrap(
        api.POST("/api/taxonomy/domains/{domain_id}/merge", {
          params: { path: { domain_id: variables.domainId } },
          body: { into: variables.into },
        }),
      ) as Promise<MatchGap>,
    "Domains merged",
  );
}
