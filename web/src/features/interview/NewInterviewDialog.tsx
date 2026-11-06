import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { Spinner } from "@/components/ui/spinner";
import { normalizePipelineStage, orderPipelineStages, pipelineStageLabel } from "@/features/pipeline/pipeline-stages";
import { api, fetchAllPages, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

import { InterviewSetupDialog } from "./InterviewSetupDialog";
import { useInterviewSessions } from "./use-interview";

type PipelineItem = components["schemas"]["PipelineItem"];
type JobDetail = components["schemas"]["JobDetail"];

function useInterviewableJobs(enabled: boolean) {
  return useQuery({
    queryKey: ["interviewable-jobs"],
    enabled,
    queryFn: async () => {
      const rows = await Promise.all((["tailored", "rendered"] as const).map((status) =>
        fetchAllPages<PipelineItem>((page) => api.GET("/api/pipeline", {
          params: { query: { status, sortBy: "recency", page, pageSize: 200 } },
        })),
      ));
      return [...new Map(rows.flat().map((job) => [job.jobId, job])).values()];
    },
  });
}

export function NewInterviewDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation();
  const [jobId, setJobId] = useState<number | null>(null);
  const jobs = useInterviewableJobs(open);
  const sessions = useInterviewSessions();
  const activeJobIds = useMemo(() => new Set(
    sessions.data?.sessions?.filter((session) => session.status === "active").map((session) => session.jobId),
  ), [sessions.data]);
  const ready = !!jobs.data && !!sessions.data;
  const loadError = (!jobs.data && jobs.isError) || (!sessions.data && sessions.isError);
  const candidates = ready ? jobs.data.filter((job) => !activeJobIds.has(job.jobId)) : [];
  const chosen = candidates.find((job) => job.jobId === jobId);
  if (ready && jobId !== null && !chosen) setJobId(null);
  const detail = useQuery({
    queryKey: ["job-detail", jobId],
    enabled: open && !!chosen,
    queryFn: () => unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: jobId as number } } })) as Promise<JobDetail>,
  });
  const close = (next: boolean) => {
    if (!next) setJobId(null);
    onOpenChange(next);
  };

  if (chosen && detail.data?.resumeVersions.length) {
    return <InterviewSetupDialog jobId={chosen.jobId} versions={detail.data.resumeVersions} open={open} onOpenChange={close} />;
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New mock interview</DialogTitle>
          <DialogDescription>Choose a tailored job. Jobs with an interview in progress are hidden so you can resume them from the sessions list.</DialogDescription>
        </DialogHeader>
        {loadError ? (
          <Alert variant="destructive">
            <AlertTitle>Could not load jobs</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
              <span>Check the connection and try again.</span>
              <Button size="sm" variant="outline" disabled={jobs.isFetching || sessions.isFetching} onClick={() => {
                if (jobs.isError) void jobs.refetch();
                if (sessions.isError) void sessions.refetch();
              }}>Try again</Button>
            </AlertDescription>
          </Alert>
        ) : !ready ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner aria-hidden />Loading jobs…</p>
        ) : candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">No jobs are ready for interview practice. Tailor a resume first.</p>
        ) : (
          <Field>
            <FieldLabel htmlFor="new-interview-job">Job</FieldLabel>
            <SearchableSelect
              id="new-interview-job"
              placeholder="Choose a job"
              searchLabel={t("longLists.searchInterviewJobs")}
              value={chosen ? String(chosen.jobId) : null}
              onChange={(id) => setJobId(Number(id))}
              groups={orderPipelineStages(new Set(candidates.map((job) => normalizePipelineStage(job.status)))).map((status) => ({
                id: status,
                label: pipelineStageLabel(status, t),
                items: candidates.filter((job) => normalizePipelineStage(job.status) === status).map((job) => ({
                  value: String(job.jobId),
                  label: [job.company, job.title].filter(Boolean).join(" · ") || t("longLists.jobId", { id: job.jobId }),
                  keywords: [status],
                })),
              }))}
            />
          </Field>
        )}
        {chosen && detail.isPending ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner aria-hidden />Loading resume versions…</p>
        ) : null}
        {chosen && detail.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Could not load resume versions</AlertTitle>
            <AlertDescription><Button size="sm" variant="outline" disabled={detail.isFetching} onClick={() => void detail.refetch()}>Try again</Button></AlertDescription>
          </Alert>
        ) : null}
        {chosen && detail.data?.resumeVersions.length === 0 ? (
          <p className="text-sm text-muted-foreground">This job has no tailored resume version yet.</p>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
