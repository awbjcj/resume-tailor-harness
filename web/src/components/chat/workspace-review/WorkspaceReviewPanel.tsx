import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useWorkspaceReviewCopy } from "@/i18n/workspace-review";
import { api, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { WorkspaceReviewProps } from "../WorkspaceReview";
import { WorkspaceProposalCard } from "./WorkspaceProposalCard";

export default function WorkspaceReviewPanel({ surface, sessionId, turnCount = 0, className }: WorkspaceReviewProps) {
  const copy = useWorkspaceReviewCopy();
  const queryClient = useQueryClient();
  const previousTurnCount = useRef(turnCount);
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["workspace-proposals", surface, sessionId, offset],
    enabled: Boolean(sessionId),
    queryFn: () => unwrap(api.GET("/api/workspace-agent/proposals", {
      params: { query: { surface, sessionId: sessionId!, offset } },
    })),
  });

  useEffect(() => {
    if (previousTurnCount.current === turnCount) return;
    previousTurnCount.current = turnCount;
    void queryClient.invalidateQueries({ queryKey: ["workspace-proposals", surface, sessionId] });
  }, [queryClient, sessionId, surface, turnCount]);

  if (!sessionId || (!offset && query.isSuccess && !query.data.proposals.length)) return null;

  return (
    <section aria-label={copy.title} className={cn("min-w-0 space-y-4", className)}>
      <div className="flex items-start gap-3">
        <ClipboardCheck className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0 space-y-1">
          <h2 className="text-sm font-semibold">{copy.title}</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">{copy.help}</p>
        </div>
      </div>
      {query.isPending ? <p role="status" className="text-sm text-muted-foreground">{copy.loading}</p> : null}
      {query.isError ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border p-3">
          <p role="alert" className="min-w-0 flex-1 text-sm text-destructive">{copy.loadFailed}</p>
          <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>{copy.retry}</Button>
        </div>
      ) : null}
      {query.data?.proposals.map((proposal) => (
        <WorkspaceProposalCard key={`${proposal.id}:${proposal.digest}`} proposal={proposal} />
      ))}
      {offset > 0 && query.isSuccess && !query.data.proposals.length ? (
        <p role="status" className="text-sm text-muted-foreground">{copy.noMore}</p>
      ) : null}
      {offset > 0 || query.data?.nextOffset != null ? (
        <nav aria-label={copy.pages} className="flex flex-wrap items-center justify-between gap-2">
          <Button variant="outline" disabled={!offset || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 20))}>{copy.previous}</Button>
          <Button variant="outline" disabled={query.data?.nextOffset == null || query.isFetching} onClick={() => setOffset(query.data!.nextOffset!)}>{copy.next}</Button>
        </nav>
      ) : null}
    </section>
  );
}
