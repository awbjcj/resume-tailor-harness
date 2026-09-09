import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSetStage } from "./use-job-mutations";
import type { JobDetail } from "./use-job-detail";

// Keep the job-detail selector aligned with every status the PATCH endpoint
// accepts. In particular, discovery can leave a job in `extracted` or
// `filtered`; omitting either makes the controlled select lose its visible
// current value.
const STAGE_VALUES = [
  "raw",
  "extracted",
  "filtered",
  "shortlisted",
  "approved",
  "tailored",
  "rendered",
  "rejected",
] as const;
const STAGE_LABEL_KEYS = {
  raw: "job.stages.raw",
  extracted: "job.stages.extracted",
  filtered: "job.stages.filtered",
  shortlisted: "job.stages.shortlisted",
  approved: "job.stages.approved",
  tailored: "job.stages.tailored",
  rendered: "job.stages.rendered",
  rejected: "job.stages.rejected",
} as const;

export function StageManager({ job }: { job: JobDetail }) {
  const { t } = useTranslation();
  const [stage, setStage] = useState(job.status);
  const setStageMut = useSetStage(job.id);
  const stageLabel = (value: string): string => {
    const labelKey = STAGE_LABEL_KEYS[value as keyof typeof STAGE_LABEL_KEYS];
    return labelKey ? t(labelKey) : value;
  };
  const stageChanged = stage !== job.status;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="mng-stage">Stage</Label>
        <Select
          value={stage}
          disabled={setStageMut.isPending}
          onValueChange={(v) => setStage(v ?? job.status)}
        >
          <SelectTrigger id="mng-stage" className="w-full">
            <SelectValue>{(value: string) => stageLabel(value)}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {STAGE_VALUES.map((s) => (
              <SelectItem key={s} value={s}>
                {stageLabel(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex gap-2">
        <Button
          type="button"
          disabled={!stageChanged || setStageMut.isPending}
          onClick={() => setStageMut.mutate(stage)}
        >
          Set stage
        </Button>
      </div>
      {(job.status === "filtered" || job.status === "rejected") &&
        stage !== "filtered" &&
        stage !== "rejected" && (
          <p className="text-xs text-muted-foreground">
            Moving this job forward overrides its discovery filter or rejection so it can be
            scored on the next discovery or shortlist re-score run.
          </p>
        )}
    </div>
  );
}
