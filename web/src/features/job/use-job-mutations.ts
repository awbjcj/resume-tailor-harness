import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, ApiError, unwrap } from "@/lib/api/client";
import { useLaunchRun } from "@/features/runs/use-launch-run";
import type { JobDetail } from "./use-job-detail";

function invalidateBoards(qc: ReturnType<typeof useQueryClient>, jobId: number) {
  const keys = [["job", jobId], ["shortlist"], ["pipeline"], ["triage"], ["dashboard-summary"]];
  return Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })));
}

export function useCheckH1BSponsorship(jobId: number) {
  const { launch } = useLaunchRun();
  return useMutation({
    mutationFn: () =>
      launch(
        "h1bSponsorship",
        () =>
          unwrap(
            api.POST("/api/jobs/{job_id}/h1b-sponsorship", {
              params: { path: { job_id: jobId } },
            }),
          ),
        // The check writes the *company-level* cache, which can change
        // sponsorship status shown for sibling jobs at the same employer on
        // every board — not just this job — so the board query keys stay
        // invalidated too (the launch default), unlike the single-job
        // scoped revise mutations below.
        undefined,
        { jobId },
      ),
  });
}

export function useRefreshCompanyIntelligence(jobId: number) {
  const { launch } = useLaunchRun();
  return useMutation({
    mutationFn: (depth: "quick" | "standard" | "deep") =>
      launch(
        "companyIntelligence",
        () =>
          unwrap(
            api.POST("/api/jobs/{job_id}/company-intelligence/refreshes", {
              params: { path: { job_id: jobId } },
              body: { depth },
            }),
          ),
        // The evidence is keyed by company, so refresh every open job detail;
        // sibling roles at the same employer share the new dossier.
        ["job", "company-intelligence-versions", "role-preparation"],
        { jobId, depth },
      ),
  });
}

export function useRefreshRolePreparation(jobId: number) {
  const { launch } = useLaunchRun();
  return useMutation({
    mutationFn: () =>
      launch(
        "rolePreparation",
        () =>
          unwrap(
            api.POST("/api/jobs/{job_id}/role-preparation-brief/refreshes", {
              params: { path: { job_id: jobId } },
            }),
          ),
        ["role-preparation"],
        { jobId },
      ),
  });
}

export function useRefreshHiringContactIntelligence(jobId: number) {
  const { launch } = useLaunchRun();
  return useMutation({
    mutationFn: () =>
      launch(
        "hiringContactIntelligence",
        () =>
          unwrap(
            api.POST("/api/jobs/{job_id}/hiring-contact-intelligence/refreshes", {
              params: { path: { job_id: jobId } },
            }),
          ),
        ["hiring-contact-intelligence"],
        { jobId },
      ),
  });
}

export function useSetStage(jobId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (status: string) =>
      unwrap(
        api.PATCH("/api/jobs/{job_id}", {
          params: { path: { job_id: jobId } },
          body: { status },
        }),
      ),
    onSuccess: () => {
      invalidateBoards(qc, jobId);
      toast.success("Stage updated");
    },
    onError: () => toast.error("Failed to update stage"),
  });
}

export function useUpsertApplication(jobId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { status: string; notes?: string | null }) =>
      unwrap(
        api.PUT("/api/jobs/{job_id}/application", {
          params: { path: { job_id: jobId } },
          body: vars,
        }),
      ),
    onSuccess: () => {
      invalidateBoards(qc, jobId);
      toast.success("Application saved");
    },
  });
}

export function useRenderVersion(jobId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ versionId, templateId }: { versionId: number; templateId?: string }) =>
      unwrap(
        api.POST("/api/resume-versions/{version_id}/render", {
          params: { path: { version_id: versionId } },
          ...(templateId ? { body: { templateId } } : {}),
        }),
      ),
    onSuccess: (version) => {
      qc.setQueryData<JobDetail>(["job", jobId], (job) => job && ({
        ...job,
        resumeVersions: job.resumeVersions.map((saved) => saved.id === version.id ? version : saved),
      }));
      void invalidateBoards(qc, jobId);
      toast.success("PDF rendered");
    },
  });
}

export function useReviseVersion(jobId: number) {
  const { launch } = useLaunchRun();
  return useMutation({
    mutationFn: (vars: { versionId: number; instruction: string; reReview?: boolean }) => {
      const reReview = vars.reReview ?? false;
      return launch(
        "revise",
        () =>
          unwrap(
            api.POST("/api/resume-versions/{version_id}/revise", {
              params: { path: { version_id: vars.versionId } },
              body: { instruction: vars.instruction, reReview },
            }),
          ),
        ["job"],
        {
          versionId: vars.versionId,
          jobId,
          instruction: vars.instruction,
          reReview,
        },
      );
    },
  });
}

export function useSelectResume(jobId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (versionId: number) =>
      unwrap(
        api.POST("/api/jobs/{job_id}/select-resume/{version_id}", {
          params: { path: { job_id: jobId, version_id: versionId } },
        }),
      ),
    onSuccess: () => invalidateBoards(qc, jobId),
    onError: (error: Error) => {
      void qc.invalidateQueries({ queryKey: ["job", jobId] });
      const ineligible = error instanceof ApiError && error.code === "MATERIAL_NOT_ELIGIBLE";
      toast.error(ineligible
        ? "This resume must pass fact-lock before you can select it for an application."
        : "Could not select this resume.");
    },
  });
}

/**
 * Clearing the application's resume selection. This is not merely the inverse
 * of selecting: it is the only way past the delete gate, since the API refuses
 * to delete a version an application still points at.
 */
export function useDeselectResume(jobId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/jobs/{job_id}/select-resume", {
          params: { path: { job_id: jobId } },
        }),
      ),
    onSuccess: () => invalidateBoards(qc, jobId),
    onError: () => toast.error("Failed to unselect"),
  });
}

export function useDeselectCoverLetter(jobId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/jobs/{job_id}/select-cover-letter", {
          params: { path: { job_id: jobId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job", jobId] }),
    onError: () => toast.error("Failed to unselect"),
  });
}

/**
 * Deleting artifacts invalidates the boards, not just the job: a row's
 * reported version count and rendered state are read straight off these
 * tables, so a board left uninvalidated would keep showing artifacts that no
 * longer exist.
 *
 * Refresh stale rows if the server reports an unavailable or selected item.
 */
function useDeleteArtifacts<TVars>(
  jobId: number,
  mutationFn: (vars: TVars) => Promise<unknown>,
  successMessage: (vars: TVars) => string,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async (_data, vars) => {
      await invalidateBoards(qc, jobId);
      toast.success(successMessage(vars));
    },
    onError: (error: Error) => {
      void qc.invalidateQueries({ queryKey: ["job", jobId] });
      const code = error instanceof ApiError ? error.code : undefined;
      if (code === "ARTIFACT_IN_USE") toast.error("Clear the application selection before deleting this item.");
      else if (code === "NOT_FOUND") toast.error("Some selected items are no longer available.");
      else toast.error("Could not delete the selected items.");
    },
  });
}

export function useDeleteVersions(jobId: number) {
  return useDeleteArtifacts(
    jobId,
    (ids: number[]) =>
      ids.length === 1
        ? unwrap(
            api.DELETE("/api/resume-versions/{version_id}", {
              params: { path: { version_id: ids[0] } },
            }),
          )
        : unwrap(api.POST("/api/resume-versions/bulk-delete", { body: { ids } })),
    deletedVersionsMessage,
  );
}

export function useDeleteCoverLetters(jobId: number) {
  return useDeleteArtifacts(
    jobId,
    (ids: number[]) =>
      ids.length === 1
        ? unwrap(
            api.DELETE("/api/cover-letters/{cover_letter_id}", {
              params: { path: { cover_letter_id: ids[0] } },
            }),
          )
        : unwrap(api.POST("/api/cover-letters/bulk-delete", { body: { ids } })),
    deletedCoverLettersMessage,
  );
}

const deletedVersionsMessage = (ids: number[]) =>
  `Deleted ${ids.length} version${ids.length === 1 ? "" : "s"}`;

const deletedCoverLettersMessage = (ids: number[]) =>
  `Deleted ${ids.length} cover letter${ids.length === 1 ? "" : "s"}`;

export function useGenerateCoverLetter(jobId: number) {
  const { launch } = useLaunchRun();
  return useMutation({
    mutationFn: () =>
      launch(
        "coverLetter",
        () =>
          unwrap(
            api.POST("/api/cover-letters", {
              body: { jobIds: [jobId], approved: false },
            }),
          ),
        // Same call the Pipeline bulk action makes, so it keeps the same board
        // invalidation: a new cover letter can change what a job's row reports.
        undefined,
        { jobId },
      ),
  });
}

export function useReviseCoverLetter(jobId: number) {
  const { launch } = useLaunchRun();
  return useMutation({
    mutationFn: (vars: { coverLetterId: number; instruction: string }) =>
      launch(
        "coverLetterRevise",
        () =>
          unwrap(
            api.POST("/api/cover-letters/{cover_letter_id}/revise", {
              params: { path: { cover_letter_id: vars.coverLetterId } },
              body: { instruction: vars.instruction, reReview: false },
            }),
          ),
        ["job"],
        { coverLetterId: vars.coverLetterId, jobId, instruction: vars.instruction },
      ),
  });
}

export function useSelectCoverLetter(jobId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (coverLetterId: number) =>
      unwrap(
        api.POST("/api/jobs/{job_id}/select-cover-letter/{cover_letter_id}", {
          params: { path: { job_id: jobId, cover_letter_id: coverLetterId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job", jobId] }),
  });
}
