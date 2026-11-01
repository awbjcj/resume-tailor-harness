import { useId } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, CircleMinus, ExternalLink } from "lucide-react";

import { ChangePreview, ReviewValue } from "@/components/approval/ChangePreview";
import { Checkbox } from "@/components/ui/checkbox";
import type { components } from "@/lib/api/schema";
import { useWorkspaceReviewCopy } from "@/i18n/workspace-review";
import { cn } from "@/lib/utils";
import { isRemovalAction } from "./action-utils";

type Action = components["schemas"]["ActionOut"];
const summaryClassName = "flex min-h-11 cursor-pointer items-center gap-2 rounded-md py-2 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden";

function isWebUrl(value: string) {
  try { return ["https:", "http:"].includes(new URL(value).protocol); }
  catch { return false; }
}

type Props = { action: Action; selected: boolean; disabled: boolean; onSelect: (checked: boolean) => void };

export function WorkspaceAction({ action, selected, disabled, onSelect }: Props) {
  const copy = useWorkspaceReviewCopy();
  const id = useId();
  const receipt = action.receipt;
  const operation = copy.operations[action.change.operation] ?? action.change.operation;
  const destructive = isRemovalAction(action);
  const StatusIcon = receipt?.state === "applied" ? CheckCircle2 : receipt?.state === "discarded" ? CircleMinus : AlertTriangle;

  return (
    <section aria-labelledby={`${id}-label`} data-selected={!receipt && selected || undefined}
      className="min-w-0 space-y-3 p-4 data-selected:bg-primary/[0.025] sm:p-5">
      <div className="flex min-h-11 items-start gap-3">
        {!receipt ? <Checkbox id={id} checked={selected} disabled={disabled} onCheckedChange={onSelect}
          className="mt-3 size-5 focus-visible:transition-none aria-disabled:cursor-not-allowed aria-disabled:opacity-50 motion-reduce:transition-none"
          aria-describedby={`${id}-reason${destructive ? ` ${id}-warning` : ""}`} /> : null}
        <label id={`${id}-label`} htmlFor={!receipt ? id : undefined}
          className={cn("flex min-h-11 min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 py-2 font-semibold", !receipt && "cursor-pointer")}>
          <span className={cn("[overflow-wrap:anywhere]", destructive && "text-destructive")}>{operation}</span>
          {action.change.job_id ? <span className="text-xs font-normal tabular-nums text-muted-foreground">{copy.job(action.change.job_id)}</span> : null}
          {action.change.target_id ? <span className="text-xs font-normal tabular-nums text-muted-foreground">{copy.record(action.change.target_id)}</span> : null}
        </label>
        {receipt ? <StatusIcon className="mt-3 size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
      </div>
      <p id={`${id}-reason`} className="text-sm leading-relaxed [overflow-wrap:anywhere]">{action.change.reason}</p>
      {destructive && !receipt ? (
        <p id={`${id}-warning`} className="flex items-start gap-2 text-sm leading-relaxed text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>{action.change.operation === "profile.change" ? copy.profileRemovalHelp : action.change.operation === "job.delete" ? copy.deleteJobHelp : copy.deleteHelp}</span>
        </p>
      ) : null}
      <details className="group/details min-w-0" open={!receipt}>
        <summary className={summaryClassName}>
          <ChevronDown className="size-4 shrink-0 -rotate-90 group-open/details:rotate-0" aria-hidden="true" />
          <span>{copy.details}</span><span className="sr-only"> · {operation}</span>
        </summary>
        <div className="min-w-0 space-y-3 pt-1">
          <ChangePreview before={action.before} after={action.after} />
          {action.change.citations?.length ? (
            <div className="min-w-0 space-y-1 text-sm">
              <p className="text-xs font-medium text-muted-foreground">{copy.sources}</p>
              <ul className="min-w-0">
                {action.change.citations.map((url, index) => (
                  <li key={`${index}:${url}`} className="min-w-0">
                    {isWebUrl(url) ? (
                      <a href={url} target="_blank" rel="noopener noreferrer" className="flex min-h-11 items-center gap-2 rounded py-2 underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring">
                        <span className="min-w-0 [overflow-wrap:anywhere]">{url}</span>
                        <ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />
                        <span className="sr-only">{copy.newTab}</span>
                      </a>
                    ) : <span className="[overflow-wrap:anywhere]">{url}</span>}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </details>
      {receipt ? (
        <div className="min-w-0 rounded-lg border bg-muted/25 p-3 text-sm">
          <p role="status" className="flex items-start gap-2 font-medium">
            <StatusIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {receipt.state === "applied" ? copy.saved : receipt.state === "discarded" ? copy.discarded : copy.unconfirmed}
          </p>
          {Object.keys(receipt.result).length ? <details className="group/result mt-1">
            <summary className={summaryClassName}>
              <ChevronDown className="size-4 shrink-0 -rotate-90 group-open/result:rotate-0" aria-hidden="true" />
              <span>{copy.result}</span><span className="sr-only"> · {operation}</span>
            </summary>
            <ReviewValue value={receipt.result} />
          </details> : null}
        </div>
      ) : null}
    </section>
  );
}
