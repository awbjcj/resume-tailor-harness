import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type SkillEntry = components["schemas"]["SkillEntryOut"];
export const SKILL_MUTATION_KEY = ["profile-skill-mutation"];

export async function invalidateSkillSurfaces(
  qc: ReturnType<typeof useQueryClient>,
) {
  await Promise.all(
    [
      "profile-skills",
      "profile-matrix",
      "skill-cleanup",
      "suppressed-skills",
      "match-gap",
      "job",
      "shortlist",
      "pipeline",
      "triage",
    ].map((key) => qc.invalidateQueries({ queryKey: [key] })),
  );
}

export function useProfileSkills(enabled = true) {
  return useQuery({
    queryKey: ["profile-skills"],
    enabled,
    queryFn: () =>
      unwrap(api.GET("/api/profile/skills", {} as never)) as Promise<
        SkillEntry[]
      >,
  });
}

export function useAddSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: (vars: components["schemas"]["UpdateProfileSkillIn"]) =>
      unwrap(api.POST("/api/profile/skills", { body: vars })),
    onSuccess: async () => {
      await invalidateSkillSurfaces(qc);
      toast.success("Added to your skills");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useAddSkillAlias() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: (vars: { skillId: string; alias: string }) =>
      unwrap(
        api.POST("/api/profile/skills/{skill_id}/aliases", {
          params: { path: { skill_id: vars.skillId } },
          body: { alias: vars.alias },
        }),
      ),
    onSuccess: async () => {
      await invalidateSkillSurfaces(qc);
      toast.success("Added to your skills");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUpdateSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: ({
      key,
      ...body
    }: components["schemas"]["UpdateProfileSkillIn"] & { key: string }) =>
      unwrap(
        api.PUT("/api/profile/skills/{key}", {
          params: { path: { key } },
          body,
        }),
      ),
    onSuccess: async () => {
      await invalidateSkillSurfaces(qc);
      toast.success("Skill updated");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useMoveSkillGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: ({ key, group }: { key: string; group: string | null }) =>
      group === null
        ? unwrap(
            api.DELETE("/api/profile/skills/{key}/group", {
              params: { path: { key } },
            }),
          )
        : unwrap(
            api.PUT("/api/profile/skills/{key}/group", {
              params: { path: { key } },
              body: { group },
            }),
          ),
    onSuccess: async (_data, variables) => {
      await invalidateSkillSurfaces(qc);
      toast.success("Skill updated");
      requestAnimationFrame(() => {
        if (document.activeElement === document.body)
          document
            .getElementById(
              `profile-skill-${encodeURIComponent(variables.key)}`,
            )
            ?.focus({ preventScroll: true });
      });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useMergeProfileSkills() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: (body: components["schemas"]["MergeProfileSkillsIn"]) =>
      unwrap(api.POST("/api/profile/skills/merge", { body })),
    onSuccess: async () => {
      await invalidateSkillSurfaces(qc);
      toast.success("Skills merged");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useSkillCleanup(enabled: boolean) {
  return useQuery({
    queryKey: ["skill-cleanup"],
    enabled,
    queryFn: () => unwrap(api.GET("/api/profile/skills/cleanup")),
  });
}

export function useCleanProfileSkills() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: () => unwrap(api.POST("/api/profile/skills/cleanup")),
    onSuccess: async () => {
      await invalidateSkillSurfaces(qc);
      toast.success("Skill cleanup complete");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useSkillCleanupPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: (enabled: boolean) =>
      unwrap(api.PATCH("/api/profile/skills/cleanup", { body: { enabled } })),
    onSuccess: () => invalidateSkillSurfaces(qc),
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useSkillOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: (vars: {
      kind: "group" | "category";
      key?: string;
      label: string;
      category?: string;
      remove?: boolean;
    }) => {
      const body = { label: vars.label, category: vars.category ?? "other" };
      if (vars.kind === "group") {
        if (!vars.key)
          return unwrap(api.POST("/api/profile/skill-groups", { body }));
        const params = { path: { key: vars.key } };
        return vars.remove
          ? unwrap(api.DELETE("/api/profile/skill-groups/{key}", { params }))
          : unwrap(
              api.PUT("/api/profile/skill-groups/{key}", { params, body }),
            );
      }
      if (!vars.key)
        return unwrap(api.POST("/api/profile/skill-categories", { body }));
      const params = { path: { key: vars.key } };
      return vars.remove
        ? unwrap(api.DELETE("/api/profile/skill-categories/{key}", { params }))
        : unwrap(
            api.PUT("/api/profile/skill-categories/{key}", { params, body }),
          );
    },
    onSuccess: async () => {
      await invalidateSkillSurfaces(qc);
      toast.success("Skill organization updated");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
