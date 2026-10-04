import { ProposalCard } from "./ProposalCard";
import type { ScoutSession } from "./use-scout";

/** References persisted proposals; inline decisions and the ledger share one
 * query cache and the same server-side approval/verification boundaries. */
export function ScoutResearchCards({ session, proposalIds }: { session: ScoutSession; proposalIds: string[] }) {
  const ids = new Set(proposalIds);
  const proposals = (session.proposals ?? []).filter((proposal) => ids.has(proposal.id));
  if (!proposals.length) return null;
  return (
    <section aria-label="Research results" className="mt-4 space-y-2 sm:ml-10">
      <p className="text-xs font-medium text-muted-foreground">Review the evidence and choose what to add.</p>
      <ul className="grid gap-3">
        {proposals.map((proposal) => <ProposalCard key={proposal.id} inline sessionId={session.sessionId} proposal={proposal} scrapeAvailable={session.scrapeAvailable ?? false} />)}
      </ul>
    </section>
  );
}
