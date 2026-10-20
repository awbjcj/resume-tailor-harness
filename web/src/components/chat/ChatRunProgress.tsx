import { Check, Loader2 } from "lucide-react";

import { useRunStore } from "@/lib/runs/store";
import type { ChatStreamStatus } from "@/lib/chat/useChatStream";

/** Report actual server progress. A finished reply is not a persisted turn. */
export function ChatRunProgress({ runId, status, reconnecting = false }: { runId: string | null; status: ChatStreamStatus; reconnecting?: boolean }) {
  const run = useRunStore((state) => runId ? state.runs[runId] : undefined);
  if (!runId || status === "done" || status === "error") return null;
  if (status === "stopped") return <p role="status" className="text-sm text-muted-foreground">Response stopped. You can retry your message.</p>;
  const settled = status === "settled";
  return (
    <div role="status" aria-live="polite" className="agent-status-enter flex items-center gap-3 rounded-xl border bg-muted/25 px-3 py-2 text-sm">
      {settled ? <Check className="agent-status-enter size-4 shrink-0 text-success" aria-hidden="true" /> : <Loader2 className="size-4 shrink-0 motion-safe:animate-spin" aria-hidden="true" />}
      <div className="min-w-0 flex-1">
        <p className="font-medium">{reconnecting ? "Reconnecting to your response" : status === "stopping" ? "Stopping the response" : settled ? "Saving the response" : run?.phase || "Preparing your response"}</p>
        {settled ? <p className="text-xs text-muted-foreground">The reply is ready. Final checks are still running.</p> : null}
      </div>
      {!settled && run?.total && run.total > 0 ? <span className="text-xs tabular-nums text-muted-foreground">{run.current ?? 0} / {run.total}</span> : null}
    </div>
  );
}
