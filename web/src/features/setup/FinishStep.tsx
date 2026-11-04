import { Check } from "lucide-react";
import "@/i18n/workflow";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { useSetupStatus } from "@/features/settings/use-setup-status";
import { useActiveRun } from "@/features/runs/use-active-run";
import { launchers, useLaunchRun } from "@/features/runs/use-launch-run";
import { useSetupContinuation } from "./use-setup-continuation";
import { consumeTaskDestination } from "@/lib/task-continuation";
import { useTranslation } from "react-i18next";

export function FinishStep() {
  const { t } = useTranslation();
  const { destination, steps } = useSetupContinuation();
  const { data: status } = useSetupStatus();
  const { launch } = useLaunchRun();
  const navigate = useNavigate();
  const run = useActiveRun("profile-build");
  const building = run ? ["queued", "running", "cancelling"].includes(run.status) : false;
  const built = status?.profile.freshness !== undefined ? status.profile.freshness === "current" : run?.status === "succeeded";
  const buildResult = run?.result as { experiences?: number; projects?: number } | null | undefined;

  return (
    <Card>
      <CardHeader>
        <CardTitle><h1>Finish setup</h1></CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-2">
          {steps.map((step) => (
            <li key={step.slug} className="flex items-center gap-2 text-sm">
              {status && step.done(status) ? (
                <Check className="size-4 text-primary" aria-hidden="true" />
              ) : (
                <span className="size-4 rounded-full border" aria-hidden="true" />
              )}
              {step.label}
            </li>
          ))}
        </ul>

        {building && (
          <div className="flex flex-col gap-2">
            <Progress value={Math.round(run?.percent ?? 0)} aria-label="Profile build progress" />
            <p className="text-sm text-muted-foreground">Building your profile…</p>
          </div>
        )}
        {built && (
          <p className="text-sm text-primary">
            {buildResult ? <>Profile built: {buildResult.experiences ?? 0} experiences,{" "}{buildResult.projects ?? 0} projects extracted.</> : t("workflow.profileReady")}
          </p>
        )}
      </CardContent>
      <CardFooter className="justify-end gap-2">
        {!built && (
          <Button variant="outline" disabled={building}
            onClick={() => launch("profile-build", () => launchers.profileBuild())}>
            {building ? <Spinner data-icon="inline-start" /> : null}
            {building ? "Building…" : "Build profile"}
          </Button>
        )}
        <Button onClick={() => {
          localStorage.setItem("resume-tailor-harness-setup-dismissed", "1");
          consumeTaskDestination();
          navigate(destination);
        }}>
          {destination === "/" ? t("workflow.dashboard") : t("workflow.returnToTask")}
        </Button>
      </CardFooter>
    </Card>
  );
}
