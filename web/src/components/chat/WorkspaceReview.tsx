import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Proposal = components["schemas"]["ProposalOut"];
type Surface = "coach" | "career-lab" | "interview" | "scout";

const operationNames: Record<string, string> = {
  "job.create": "Add job", "job.update": "Update job", "job.archive": "Archive job",
  "job.restore": "Restore job", "job.delete": "Delete job", "application.update": "Update application",
  "event.create": "Add timeline event", "event.update": "Edit event", "event.delete": "Delete event",
  "note.create": "Add note", "note.update": "Update note", "note.delete": "Remove note",
  "preparation.save": "Save preparation", "profile.change": "Update profile",
  "application_profile.update": "Edit application profile", "question.create": "Save question",
  "question.update": "Update answer", "question.delete": "Delete question",
  "artifact.select": "Select document", "artifact.delete": "Delete document", "search.update": "Update search preferences",
};

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">None</span>;
  if (Array.isArray(value)) return <ul className="space-y-2">{value.map((item, index) => <li key={index}><Value value={item} /></li>)}</ul>;
  if (typeof value === "object") return <dl className="space-y-2">{Object.entries(value).map(([key, item]) => (
    <div key={key}><dt className="font-medium capitalize">{key.replaceAll("_", " ")}</dt><dd className="pl-3"><Value value={item} /></dd></div>
  ))}</dl>;
  return <span className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{String(value)}</span>;
}

function ReviewCard({ proposal }: { proposal: Proposal }) {
  const queryClient = useQueryClient();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const pending = proposal.actions.filter((action) => !action.receipt);
  const [selection, setSelection] = useState<string[]>(pending.map((action) => action.id));
  const selected = selection.filter((id) => pending.some((action) => action.id === id));
  const review = useMutation({
    mutationFn: (decision: "apply" | "discard") => unwrap(api.POST("/api/workspace-agent/proposals/{proposal_id}/review", {
      params: { path: { proposal_id: proposal.id } }, body: { digest: proposal.digest, actionIds: selected, decision },
    })),
    onSuccess: () => { void queryClient.invalidateQueries(); },
    onError: (error: Error) => { toast.error(error.message); void queryClient.invalidateQueries({ queryKey: ["workspace-proposals"] }); },
  });
  const expired = Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(proposal.expiresAt) ? proposal.expiresAt : `${proposal.expiresAt}Z`) < now;
  return <Card className="min-w-0">
    <CardHeader><CardTitle className="text-base">{proposal.title}</CardTitle>
      <p className="text-sm text-muted-foreground">Review the exact changes below. Nothing is applied until you approve.</p>
    </CardHeader>
    <CardContent className="space-y-4">
      {proposal.actions.map((action) => <section key={action.id} className="space-y-2 rounded-lg border p-3">
        <label className="flex items-start gap-2 font-medium">
          {!action.receipt ? <input type="checkbox" checked={selected.includes(action.id)} disabled={review.isPending || expired}
            onChange={(event) => setSelection((current) => event.target.checked ? [...current, action.id] : current.filter((id) => id !== action.id))} /> : null}
          <span>{operationNames[action.change.operation] ?? action.change.operation}{action.change.job_id ? ` · #${action.change.job_id}` : ""}</span>
        </label>
        <p className="text-sm">{action.change.reason}</p>
        {action.change.operation === "job.delete" ? <p className="text-sm text-destructive">Deleting this job also removes its practice conversations.</p> : null}
        <details className="text-sm" open={!action.receipt}><summary className="cursor-pointer font-medium">Details</summary>
          <div className="mt-2 grid min-w-0 gap-3 sm:grid-cols-2">
            <div className="min-w-0 rounded bg-muted/40 p-3"><p className="mb-2 font-semibold">Before</p><Value value={action.before} /></div>
            <div className="min-w-0 rounded bg-muted/40 p-3"><p className="mb-2 font-semibold">After</p><Value value={action.after} /></div>
          </div>
        </details>
        {action.change.citations?.length ? <ul className="space-y-1 text-sm">{action.change.citations.map((url) => <li key={url}><a href={url} target="_blank" rel="noopener noreferrer" className="break-all underline">{url}</a></li>)}</ul> : null}
        {action.receipt ? <div role="status" className="text-sm">
          <p className="font-medium">{action.receipt.state === "applied" ? "Saved" : action.receipt.state === "discarded" ? "Changes discarded" : "Outcome unconfirmed — do not retry"}</p>
          <details><summary className="cursor-pointer">Result</summary><Value value={action.receipt.result} /></details>
        </div> : null}
      </section>)}
      {pending.length ? <div className="flex flex-wrap items-center gap-2">
        <Button disabled={!selected.length || review.isPending || expired} onClick={() => review.mutate("apply")}>Approve and save</Button>
        <Button variant="outline" disabled={!selected.length || review.isPending} onClick={() => review.mutate("discard")}>Discard</Button>
        {expired ? <p className="text-sm text-muted-foreground">This proposal expired. Ask the agent for a fresh preview.</p> : null}
      </div> : null}
      {review.isError ? <p role="alert" className="text-sm text-destructive">{review.error.message}</p> : null}
    </CardContent>
  </Card>;
}

type Props = { surface: Surface; sessionId?: string | null; turnCount?: number };

export function WorkspaceReview(props: Props) {
  return <WorkspaceReviewPage key={`${props.surface}-${props.sessionId}-${props.turnCount}`} {...props} />;
}

function WorkspaceReviewPage({ surface, sessionId, turnCount = 0 }: Props) {
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["workspace-proposals", surface, sessionId, turnCount, offset],
    enabled: Boolean(sessionId),
    queryFn: () => unwrap(api.GET("/api/workspace-agent/proposals", { params: { query: { surface, sessionId: sessionId!, offset } } })),
  });
  if (!sessionId) return null;
  if (query.isError) return <p role="alert" className="text-sm text-destructive">Unable to load proposed changes. <Button variant="ghost" onClick={() => void query.refetch()}>Retry</Button></p>;
  if (!query.data?.proposals.length) return null;
  return <div className="max-h-[70vh] min-w-0 space-y-3 overflow-y-auto p-4" aria-label="Awaiting review">
    {query.data.proposals.map((proposal) => <ReviewCard key={proposal.id} proposal={proposal} />)}
    <div className="flex gap-2">
      {offset > 0 ? <Button variant="outline" onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</Button> : null}
      {query.data.nextOffset != null ? <Button variant="outline" onClick={() => setOffset(query.data.nextOffset!)}>Next</Button> : null}
    </div>
  </div>;
}
