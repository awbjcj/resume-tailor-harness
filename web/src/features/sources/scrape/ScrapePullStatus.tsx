import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ScrapeImport } from "./ScrapeImport";

export function ScrapePullStatus({ runId }: { runId: string }) {
  const query = useQuery({
    queryKey: ["public-pull", runId],
    enabled: !!runId,
    queryFn: () =>
      unwrap(
        api.GET("/api/runs/{run_id}", { params: { path: { run_id: runId } } }),
      ),
    refetchInterval: (query) =>
      ["done", "error", "cancelled"].includes(query.state.data?.state ?? "")
        ? false
        : 1500,
  });
  if (!runId) return null;
  const result = query.data?.result;
  if (query.error || query.data?.error)
    return (
      <p role="alert" className="w-full text-sm text-destructive">
        {query.error?.message || query.data?.error}
      </p>
    );
  if (!result || typeof result !== "object" || Array.isArray(result))
    return (
      <p role="status" className="w-full text-sm">
        {query.data?.label || "Inspecting public page…"}
      </p>
    );
  const report = result as Record<string, unknown>;
  return (
    <div role="status" className="w-full space-y-2 text-sm">
      <p>
        {String(report.imported ?? 0)} imported ·{" "}
        {String(report.duplicate ?? 0)} duplicates ·{" "}
        {String(report.reviewNeeded ?? 0)} need review
      </p>
      {Array.isArray(report.messages) &&
        report.messages.map((message, i) => (
          <p key={i} className="text-muted-foreground">
            {String(message)}
          </p>
        ))}
      {typeof report.repairDraftId === "string" && (
        <ScrapeImport
          initialDraftId={report.repairDraftId}
          label="Review updated rules"
        />
      )}
    </div>
  );
}
