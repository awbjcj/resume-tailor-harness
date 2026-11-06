import { useId, useState } from "react";
import { RotateCcw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { dismissArtifactRun, resumeRevisionLifecycle } from "./artifact-runs";
import { useReviseVersion } from "./use-job-mutations";

export function ResumeRevisionEditor({
  jobId, versionId, revision, disabled,
}: {
  jobId: number;
  versionId: number;
  revision: ReturnType<typeof resumeRevisionLifecycle>;
  disabled?: boolean;
}) {
  const [instruction, setInstruction] = useState("");
  const [reReview, setReReview] = useState(false);
  const checkboxId = useId();
  const instructionId = useId();
  const revise = useReviseVersion(jobId);
  const busy = disabled || revision.active || revise.isPending;
  const run = revision.run;
  const retryInput = revision.retryInput;

  return (
    <div className="space-y-2">
      <details>
        <summary className="w-fit cursor-pointer rounded-sm text-sm font-medium text-muted-foreground focus-visible:outline focus-visible:outline-ring">Revise content</summary>
        <form className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-end" onSubmit={(event) => {
          event.preventDefault();
          if (!busy && instruction.trim()) {
            revise.mutate({ versionId, instruction: instruction.trim(), reReview }, { onSuccess: () => setInstruction("") });
          }
        }}>
          <div className="grid min-w-0 gap-1.5">
            <Label htmlFor={instructionId}>Resume revision instruction</Label>
            <Input
              id={instructionId}
              className="h-11"
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="Revise this version"
              disabled={busy}
            />
          </div>
          <label htmlFor={checkboxId} className="flex min-h-11 items-center gap-2 text-sm text-muted-foreground">
            <Checkbox id={checkboxId} checked={reReview} disabled={busy} onCheckedChange={(value) => setReReview(Boolean(value))} />
            Re-review
          </label>
          <Button type="submit" size="sm" className="min-h-11" disabled={!instruction.trim() || busy}>
            {revise.isPending ? <Spinner data-icon="inline-start" aria-hidden="true" /> : <RotateCcw data-icon="inline-start" aria-hidden="true" />}
            Revise
          </Button>
        </form>
      </details>
      {revision.active && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Spinner data-icon="inline-start" aria-hidden="true" />
          Revision in progress
        </p>
      )}
      {run?.status === "failed" && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-destructive" role="alert">
          <span>Revision failed: {run.error ?? "unknown error"}</span>
          {retryInput && (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => revise.mutate(retryInput)}>
              <RotateCcw data-icon="inline-start" aria-hidden="true" />
              Retry
            </Button>
          )}
          <Button size="icon-sm" variant="ghost" aria-label="Dismiss revision error" onClick={() => dismissArtifactRun(run.runId)}>
            <X aria-hidden="true" />
          </Button>
        </div>
      )}
    </div>
  );
}
