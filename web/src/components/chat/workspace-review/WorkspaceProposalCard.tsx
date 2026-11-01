import { useEffect, useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useWorkspaceReviewCopy } from "@/i18n/workspace-review";
import { WorkspaceAction } from "./WorkspaceAction";

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
  const titleId = useId();
  const expired = useExpired(proposal.expiresAt);
  const pending = proposal.actions.filter((action) => !action.receipt);
  const [selection, setSelection] = useState(() => pending.map((action) => action.id));
  const selected = selection.filter((id) => pending.some((action) => action.id === id));
  const review = useMutation({
    mutationFn: (decision: "apply" | "discard") => unwrap(api.POST("/api/workspace-agent/proposals/{proposal_id}/review", {
      params: { path: { proposal_id: proposal.id } },
      body: { digest: proposal.digest, actionIds: selected, decision },
    })),
    onSuccess: async (updated) => {
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

  return (
    <Card role="group" aria-labelledby={titleId} className="@container/proposal min-w-0 gap-0 border shadow-none ring-0">
      <CardHeader className="pb-3">
        <h3 id={titleId} className="text-base font-semibold leading-snug [overflow-wrap:anywhere]">{proposal.title}</h3>
      </CardHeader>
      <CardContent className="divide-y border-t px-0">
        {proposal.actions.map((action) => (
          <WorkspaceAction
            key={action.id}
            action={action}
            selected={selected.includes(action.id)}
            disabled={review.isPending}
            onSelect={(checked) => setSelection((current) => checked ? [...current, action.id] : current.filter((id) => id !== action.id))}
          />
        ))}
      </CardContent>
      {pending.length ? (
        <CardFooter className="flex-col items-stretch gap-3">
          <p role="status" className="text-sm tabular-nums text-muted-foreground">
            {review.isPending
              ? review.variables === "apply" ? copy.saving : copy.discarding
              : copy.selection(selected.length, pending.length)}
          </p>
          {expired ? <p className="text-sm text-muted-foreground">This proposal expired. Ask the agent for a fresh preview.</p> : null}
          {!selected.length ? <p className="text-sm text-muted-foreground">{copy.select}</p> : null}
          <div className="flex flex-col gap-2 @sm/proposal:flex-row @sm/proposal:flex-wrap">
            <Button className="h-auto min-h-11 whitespace-normal py-2" disabled={!selected.length || review.isPending || expired} onClick={() => review.mutate("apply")}>
              {review.isPending && review.variables === "apply" ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
              Approve and save
            </Button>
            <Button className="h-auto min-h-11 whitespace-normal py-2" variant="outline" disabled={!selected.length || review.isPending} onClick={() => review.mutate("discard")}>
              {review.isPending && review.variables === "discard" ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : null}
              Discard
            </Button>
          </div>
        </CardFooter>
      ) : null}
      {review.isError ? <p role="alert" className="px-4 pt-3 text-sm text-destructive [overflow-wrap:anywhere]">{review.error.message}</p> : null}
    </Card>
  );
}
