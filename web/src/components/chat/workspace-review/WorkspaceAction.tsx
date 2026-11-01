import { useId } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, CircleMinus, ExternalLink } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import type { components } from "@/lib/api/schema";
import { useWorkspaceReviewCopy } from "@/i18n/workspace-review";
import { cn } from "@/lib/utils";

type Action = components["schemas"]["ActionOut"];

const operationNames: Record<Action["change"]["operation"], string> = {
  "job.create": "Add job",
  "job.update": "Update job",
  "job.archive": "Archive job",
  "job.restore": "Restore job",
  "job.delete": "Delete job",
  "application.update": "Update application",
  "event.create": "Add timeline event",
  "event.update": "Edit event",
  "event.delete": "Delete event",
  "note.create": "Add note",
  "note.update": "Update note",
  "note.delete": "Remove note",
  "preparation.save": "Save preparation",
  "profile.change": "Update profile",
  "application_profile.update": "Edit application profile",
  "question.create": "Save question",
  "question.update": "Update answer",
  "question.delete": "Delete question",
  "artifact.select": "Select document",
  "artifact.delete": "Delete document",
  "search.update": "Update search preferences",
};

const summaryClassName = "flex min-h-11 cursor-pointer items-center gap-2 rounded-md py-2 font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden";

function ProposalValue({ value, copy }: { value: unknown; copy: ReturnType<typeof useWorkspaceReviewCopy> }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">None</span>;
  if (value === "") return <span className="text-muted-foreground">{copy.emptyText}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-muted-foreground">{copy.emptyList}</span>;
    return <ul className="min-w-0 space-y-2 border-l pl-3">{value.map((item, index) => <li key={index}><ProposalValue value={item} copy={copy} /></li>)}</ul>;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) return <span className="text-muted-foreground">{copy.noFields}</span>;
    return (
      <dl className="min-w-0 space-y-3">
        {entries.map(([key, item]) => (
          <div key={key} className="min-w-0 space-y-1">
            <dt className="font-medium capitalize [overflow-wrap:anywhere]">{key.replaceAll("_", " ")}</dt>
            <dd className="min-w-0"><ProposalValue value={item} copy={copy} /></dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span className="whitespace-pre-wrap [overflow-wrap:anywhere]">{String(value)}</span>;
}

function isWebUrl(value: string) {
  try {
    return ["https:", "http:"].includes(new URL(value).protocol);
  } catch {
    return false;
  }
}

type Props = { action: Action; selected: boolean; disabled: boolean; onSelect: (checked: boolean) => void };

export function WorkspaceAction({ action, selected, disabled, onSelect }: Props) {
  const copy = useWorkspaceReviewCopy();
  const id = useId();
  const receipt = action.receipt;
  const operation = operationNames[action.change.operation] ?? action.change.operation;
  const destructive = action.change.operation.endsWith(".delete");
  const StatusIcon = receipt?.state === "applied" ? CheckCircle2 : receipt?.state === "discarded" ? CircleMinus : AlertTriangle;

  return (
    <section aria-labelledby={`${id}-label`} className="min-w-0 space-y-2 px-4 py-3">
      <div className="flex min-h-11 items-start gap-3">
        {!receipt ? <Checkbox id={id} checked={selected} disabled={disabled} onCheckedChange={onSelect} className="mt-3 size-5 focus-visible:transition-none aria-disabled:cursor-not-allowed aria-disabled:opacity-50 motion-reduce:transition-none" aria-describedby={`${id}-reason`} /> : null}
        <label id={`${id}-label`} htmlFor={!receipt ? id : undefined} className={cn("flex min-h-11 min-w-0 flex-1 flex-wrap items-center gap-x-2 py-2 font-medium", !receipt && "cursor-pointer")}>
          <span className={cn("[overflow-wrap:anywhere]", destructive && "text-destructive")}>{operation}</span>{" "}
          {action.change.job_id ? <span className="text-xs tabular-nums text-muted-foreground">{`Job #${action.change.job_id}`}</span> : null}
        </label>
      </div>
      <p id={`${id}-reason`} className="text-sm leading-relaxed [overflow-wrap:anywhere]">{action.change.reason}</p>
      {action.change.operation === "job.delete" ? (
        <p className="flex items-start gap-2 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Deleting this job also removes its practice conversations.
        </p>
      ) : null}
      <details className="group/details text-sm" open={!receipt}>
        <summary className={summaryClassName}>
          <ChevronDown className="size-4 shrink-0 -rotate-90 group-open/details:rotate-0" aria-hidden="true" />
          <span>Details</span><span className="sr-only"> · {operation}</span>
        </summary>
        <div className="grid min-w-0 gap-3 @lg/proposal:grid-cols-2">
          <div className="min-w-0 space-y-3 rounded-lg border bg-muted/25 p-3">
            <p className="text-xs font-semibold text-muted-foreground">Before</p>
            <ProposalValue value={action.before} copy={copy} />
          </div>
          <div className="min-w-0 space-y-3 rounded-lg border p-3">
            <p className="text-xs font-semibold text-muted-foreground">After</p>
            <ProposalValue value={action.after} copy={copy} />
          </div>
        </div>
      </details>
      {action.change.citations?.length ? (
        <div className="min-w-0 space-y-1 pt-1 text-sm">
          <p className="text-xs font-medium text-muted-foreground">Sources</p>
          <ul className="min-w-0">
            {action.change.citations.map((url, index) => (
              <li key={`${index}:${url}`} className="min-w-0">
                {isWebUrl(url) ? (
                  <a href={url} target="_blank" rel="noopener noreferrer" className="flex min-h-9 items-center gap-2 rounded py-1 underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring">
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
      {receipt ? (
        <div className="space-y-1 rounded-lg bg-muted/40 p-3 text-sm">
          <p role="status" className="flex items-start gap-2 font-medium">
            <StatusIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {receipt.state === "applied" ? "Saved" : receipt.state === "discarded" ? "Changes discarded" : copy.unconfirmed}
          </p>
          <details className="group/result">
            <summary className={summaryClassName}>
              <ChevronDown className="size-4 shrink-0 -rotate-90 group-open/result:rotate-0" aria-hidden="true" />
              <span>Result</span><span className="sr-only"> · {operation}</span>
            </summary>
            <ProposalValue value={receipt.result} copy={copy} />
          </details>
        </div>
      ) : null}
    </section>
  );
}
