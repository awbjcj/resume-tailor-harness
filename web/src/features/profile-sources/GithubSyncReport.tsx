import { useProfileOperation } from "./use-profile-operation";

type SyncReport = {
  written?: string[];
  removed?: string[];
  failures?: Record<string, string>;
  warnings?: string[];
};

export function GithubSyncReport() {
  const run = useProfileOperation("github-sync");
  if (!run || !["succeeded", "failed", "cancelled"].includes(run.status))
    return null;
  const report = run.result as SyncReport | undefined;
  const failures = Object.entries(report?.failures ?? {});
  const warnings = report?.warnings ?? [];
  const hasIssues =
    run.status === "failed" || failures.length > 0 || warnings.length > 0;
  const cancelled = run.status === "cancelled";
  return (
    <div
      role={hasIssues ? "alert" : "status"}
      className="space-y-2 rounded-lg border border-border bg-muted/20 p-4 text-sm"
    >
      <p className="font-medium">
        {hasIssues
          ? "Some GitHub sources could not sync"
          : cancelled
            ? "GitHub sync cancelled"
            : "GitHub sync complete"}
      </p>
      {run.error ? (
        <p className="text-destructive [overflow-wrap:anywhere]">{run.error}</p>
      ) : null}
      {report ? (
        <p className="tabular-nums">{`${report.written?.length ?? 0} sources updated · ${report.removed?.length ?? 0} sources removed`}</p>
      ) : null}
      {hasIssues ? (
        <p>
          Saved copies are kept when a repository cannot be read. Check your
          branch selection and GitHub access, then sync again.
        </p>
      ) : cancelled ? (
        <p>Sync again to finish updating your project sources.</p>
      ) : (
        <p>Build your profile to include new or updated project evidence.</p>
      )}
      {failures.length || warnings.length ? (
        <ul className="space-y-1 text-muted-foreground [overflow-wrap:anywhere]">
          {failures.map(([repo, reason]) => (
            <li key={repo}>
              {repo}: {reason}
            </li>
          ))}
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
