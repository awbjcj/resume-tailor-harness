import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import {
  invalidateSkillSurfaces,
  SKILL_MUTATION_KEY,
} from "@/features/profile-skills/use-profile-skills";

export type ProfileMatrix = components["schemas"]["MatrixOut"];
export type SuppressedSkill = components["schemas"]["SuppressedSkillOut"];

/** Every surface where a skill's presence or coverage is displayed. */
export function useMatrix() {
  return useQuery({
    queryKey: ["profile-matrix"],
    queryFn: () =>
      unwrap(
        api.GET("/api/profile/matrix", {} as never),
      ) as Promise<ProfileMatrix>,
  });
}

export function useSuppressedSkills() {
  return useQuery({
    queryKey: ["suppressed-skills"],
    queryFn: () =>
      unwrap(api.GET("/api/profile/suppressed-skills", {} as never)) as Promise<
        SuppressedSkill[]
      >,
  });
}

export function useDeleteSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: (key: string) =>
      unwrap(
        api.DELETE("/api/profile/skills/{key}", { params: { path: { key } } }),
      ),
    onSuccess: async () => {
      await invalidateSkillSurfaces(queryClient);
      toast.success("Skill deleted");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useRestoreSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: SKILL_MUTATION_KEY,
    mutationFn: (token: string) =>
      unwrap(
        api.POST("/api/profile/suppressed-skills/{token}/restore", {
          params: { path: { token } },
        }),
      ),
    onSuccess: async () => {
      await invalidateSkillSurfaces(queryClient);
      toast.success("Skill restored");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
