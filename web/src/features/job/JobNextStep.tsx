import { Link } from "react-router-dom";
import "@/i18n/workflow";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useSetupStatus } from "@/features/settings/use-setup-status";
import { useBulkRun } from "@/features/runs/use-bulk-run";
import { useApprove } from "@/features/shortlist/use-approve";
import { useRunStore } from "@/lib/runs/store";
import { withTaskDestination } from "@/lib/task-continuation";
import { runCoversJob } from "./artifact-runs";
import { useRenderVersion } from "./use-job-mutations";
import { CopyApplicationPromptButton } from "./CopyApplicationPromptButton";
import type { JobDetail } from "./use-job-detail";

export function JobNextStep({ job, onTab }: { job: Pick<JobDetail, "id" | "nextStep">; onTab: (tab: string) => void }) {
  const { t } = useTranslation();
  const setup = useSetupStatus();
  const runs = useBulkRun();
  const approve = useApprove();
  const render = useRenderVersion(job.id);
  const runMap = useRunStore((s) => s.runs);
  const [starting, setStarting] = useState(false);
  const step = job.nextStep;
  if (!step) return null;
  const busy = Object.values(runMap).some((run) => ["queued", "running", "cancelling"].includes(run.status) && runCoversJob(run, job.id));
  const requiresSetup = step.kind === "tailor" && setup.data && (!setup.data.secrets.anyLlmKey || !setup.data.profile.factsBuiltAt || setup.data.profile.freshness === "refresh-needed");
  const continueTask = () => {
    if (step.kind === "approve") {
      approve.mutate(job.id);
      return;
    }
    if (step.kind === "track") {
      onTab("tracking");
      return;
    }
    if (step.kind === "triage") {
      onTab("job");
      return;
    }
    onTab("resumes");
    if (step.kind === "tailor") {
      setStarting(true);
      void runs.tailorSelected([job.id], false).finally(() => setStarting(false));
    } else if (step.kind === "render" && step.resumeVersionId) {
      render.mutate(step.resumeVersionId);
    }
  };

  let action;
  if (requiresSetup) {
    action = <Button size="sm" render={<Link to={withTaskDestination("/setup", step.href)} />}>
      {t("workflow.setup")}
    </Button>;
  } else if (step.kind === "apply") {
    action = <CopyApplicationPromptButton jobId={job.id} />;
  } else {
    action = <Button size="sm" disabled={busy || starting || approve.isPending || render.isPending} onClick={continueTask}>
      {busy || starting ? t("workflow.running") : t(`workflow.next.${step.kind}`)}
    </Button>;
  }

  return (
    <section className="flex flex-wrap items-center justify-between gap-3 border-b bg-primary/5 px-5 py-3 sm:px-8" aria-label={t("workflow.nextStep")}>
      <div className="min-w-0 flex-1 text-sm">
        <span className="font-semibold">{t("workflow.nextStep")}: </span>
        {t(`workflow.hint.${step.kind}`)}
      </div>
      {action}
      {render.error && <p className="w-full text-sm text-destructive" role="alert">{render.error.message}</p>}
    </section>
  );
}
