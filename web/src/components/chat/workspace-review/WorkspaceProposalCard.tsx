import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Loader2 } from "lucide-react";

import { ReviewCard } from "@/components/approval/ReviewCard";
import { ConfirmChangesDialog } from "@/components/approval/ConfirmChangesDialog";
import { Button } from "@/components/ui/button";
import { ApiError, api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useWorkspaceReviewCopy } from "@/i18n/workspace-review";
import { WorkspaceAction } from "./WorkspaceAction";
import { actionTargetNames, isRemovalAction } from "./action-utils";

type Proposal = components["schemas"]["ProposalOut"];
type ProposalPage = components["schemas"]["ProposalPage"];

function useExpired(expiresAt: string) {
  const expires = Date.parse(/(?:[zZ]|[+-]\d\d:\d\d)$/.test(expiresAt) ? expiresAt : `${expiresAt}Z`);
  const [now, setNow] = useState(Date.now);
  const expired = !Number.isFinite(expires) || expires <= now;
  useEffect(() => {
    if (expired) return;
    // Sleep until expiry instead of rerendering every card on a polling interval.
    const timer = window.setTimeout(() => setNow(Date.now()), Math.min(expires - now, 2_147_483_647));
    return () => window.clearTimeout(timer);
  }, [expired, expires, now]);
  return expired;
}

export function WorkspaceProposalCard({ proposal }: { proposal: Proposal }) {
  const copy = useWorkspaceReviewCopy();
  const queryClient = useQueryClient();
  const approveRef = useRef<HTMLButtonElement>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);
  const [confirming, setConfirming] = useState(false);
  const expired = useExpired(proposal.expiresAt);
  const pending = proposal.actions.filter((action) => !action.receipt);
  const [selection, setSelection] = useState(() => pending.filter((action) => !isRemovalAction(action)).map((action) => action.id));
  const selected = selection.filter((id) => pending.some((action) => action.id === id));
  const deletions = pending.filter((action) => selected.includes(action.id) && isRemovalAction(action));
  const unconfirmed = proposal.actions.some((action) => action.receipt?.state === "unconfirmed");
  const review = useMutation({
    mutationFn: ({ decision, actionIds }: { decision: "apply" | "discard"; actionIds: string[] }) => unwrap(api.POST("/api/workspace-agent/proposals/{proposal_id}/review", {
      params: { path: { proposal_id: proposal.id } },
      body: { digest: proposal.digest, actionIds, decision },
    })),
    onSuccess: async (updated) => {
      setConfirming(false);
      // Show the server receipt immediately, including partially resolved plans.
      queryClient.setQueriesData<ProposalPage>({ queryKey: ["workspace-proposals"] }, (page) => page && ({
        ...page,
        proposals: page.proposals.map((item) => item.id === updated.id ? updated : item),
      }));
      // Workspace operations can affect profile, jobs, tracking and settings.
      await queryClient.invalidateQueries();
    },
    onError: () => { void queryClient.invalidateQueries({ queryKey: ["workspace-proposals"] }); },
  });
  const conflict = review.error instanceof ApiError && review.error.code === "WORKSPACE_REVIEW_CONFLICT";
  const errorMessage = conflict ? copy.conflict : copy.reviewFailed;
  const submit = (decision: "apply" | "discard") => {
    if (!selected.length || review.isPending || (decision === "apply" && (expired || conflict))) return;
    review.mutate({ decision, actionIds: [...selected] });
  };
  const status = unconfirmed ? copy.unconfirmedLabel : pending.length ? expired ? copy.expired : copy.pending(pending.length) : copy.reviewed;

  return (
    <>
    <ReviewCard title={proposal.title} status={status} busy={review.isPending}
      tone={unconfirmed || expired && pending.length ? "warning" : pending.length ? "info" : "neutral"}
      footer={<>
        <p ref={statusRef} tabIndex={-1} role="status" aria-atomic="true" className="text-sm tabular-nums text-muted-foreground outline-none">
          {review.isPending ? review.variables?.decision === "apply" ? copy.saving : copy.discarding
            : pending.length ? copy.selection(selected.length, pending.length) : unconfirmed ? copy.unconfirmed : copy.allReviewed}
        </p>
        {pending.length ? <>
          {expired ? <p className="text-sm leading-relaxed text-muted-foreground">{copy.expiredHelp}</p> : null}
          {!selected.length ? <p className="text-sm text-muted-foreground">{copy.select}</p> : null}
          {review.isError && !confirming ? <p role="alert" className="text-sm leading-relaxed text-destructive [overflow-wrap:anywhere]">{errorMessage}</p> : null}
          <div className="flex flex-col gap-2 @sm/review:flex-row @sm/review:flex-wrap">
            <Button ref={approveRef} className="h-auto min-h-11 whitespace-normal py-2" disabled={!selected.length || review.isPending || expired || conflict}
              onClick={() => deletions.length ? setConfirming(true) : submit("apply")}>
              {review.isPending && review.variables?.decision === "apply" ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
              {copy.approve}
            </Button>
            <Button className="h-auto min-h-11 whitespace-normal py-2" variant="outline" disabled={!selected.length || review.isPending} onClick={() => submit("discard")}>
              {review.isPending && review.variables?.decision === "discard" ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : null}
              {copy.discard}
            </Button>
          </div>
        </> : null}
      </>}>
      {pending.length > 1 ? <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 border-b px-4 py-1 sm:px-5">
        <Button variant="link" className="min-h-11 max-w-full whitespace-normal px-0 text-sm" disabled={review.isPending || selected.length === pending.length}
          onClick={() => setSelection(pending.map((action) => action.id))}>{copy.selectAll}</Button>
        <Button variant="link" className="min-h-11 max-w-full whitespace-normal px-0 text-sm text-muted-foreground" disabled={review.isPending || !selected.length}
          onClick={() => setSelection([])}>{copy.clearSelection}</Button>
      </div> : null}
      <div className="divide-y">
        {proposal.actions.map((action) => (
          <WorkspaceAction
            key={action.id}
            action={action}
            selected={selected.includes(action.id)}
            disabled={review.isPending || confirming}
            onSelect={(checked) => setSelection((current) => checked ? [...new Set([...current, action.id])] : current.filter((id) => id !== action.id))}
          />
        ))}
      </div>
      {pending.some(isRemovalAction) ? <p className="px-4 pb-4 text-xs leading-relaxed text-muted-foreground sm:px-5">{copy.deleteSelectionHelp}</p> : null}
    </ReviewCard>
    <ConfirmChangesDialog open={confirming} onOpenChange={setConfirming}
      title={copy.confirmTitle} description={copy.confirmHelp} confirmLabel={copy.confirmAction} cancelLabel={copy.cancel}
      busy={review.isPending} disabled={!deletions.length || expired || conflict} onConfirm={() => submit("apply")}
      finalFocus={() => approveRef.current ?? statusRef.current} error={expired ? copy.expiredHelp : review.isError ? errorMessage : undefined}>
        <ul className="space-y-2 text-sm">
          {deletions.map((action) => <li key={action.id} className="flex min-w-0 items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
            <div className="min-w-0 space-y-1 [overflow-wrap:anywhere]">
              <p className="font-medium">{copy.operations[action.change.operation]}{action.change.job_id ? ` · ${copy.job(action.change.job_id)}` : ""}{action.change.target_id ? ` · ${copy.record(action.change.target_id)}` : ""}</p>
              {actionTargetNames(action).map((name, index) => <p key={index} className="text-muted-foreground">{name}</p>)}
            </div>
          </li>)}
        </ul>
    </ConfirmChangesDialog>
    </>
  );
}
