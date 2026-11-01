import { lazy, Suspense } from "react";

import type { components } from "@/lib/api/schema";
import { cn } from "@/lib/utils";

const WorkspaceReviewPanel = lazy(() => import("./workspace-review/WorkspaceReviewPanel"));

export type WorkspaceReviewProps = {
  surface: components["schemas"]["ProposalOut"]["surface"];
  sessionId?: string | null;
  turnCount?: number;
  className?: string;
};

export function WorkspaceReview(props: WorkspaceReviewProps) {
  if (!props.sessionId) return null;
  return (
    <Suspense fallback={<p role="status" className={cn("text-sm text-muted-foreground", props.className)}>Loading</p>}>
      {/* Only a different conversation resets pagination and review selections. */}
      <WorkspaceReviewPanel key={`${props.surface}:${props.sessionId}`} {...props} />
    </Suspense>
  );
}
