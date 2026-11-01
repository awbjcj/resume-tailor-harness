import { useTranslation } from "react-i18next";

import { githubSyncFailureLabel, profileBuildReportLineLabel } from "@/i18n/profile-build-diagnostics";
import { useProfileOperation } from "./use-profile-operation";

type SyncReport = {
  written?: string[];
  removed?: string[];
  failures?: Record<string, string>;
  warnings?: string[];
};

export function GithubSyncReport() {
  const { t, i18n } = useTranslation();
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
        {cancelled
          ? "GitHub sync cancelled"
          : hasIssues
            ? "GitHub sync needs attention"
            : "GitHub sync complete"}
      </p>
      {run.error ? (
        <p className="text-destructive [overflow-wrap:anywhere]">{githubSyncFailureLabel(run.error, i18n.resolvedLanguage)}</p>
      ) : null}
      {report ? (
        <p className="tabular-nums">{`${report.written?.length ?? 0} sources updated · ${report.removed?.length ?? 0} sources removed`}</p>
      ) : null}
      {cancelled ? (
        <p>Sync again to finish updating your project sources.</p>
      ) : hasIssues ? (
        <p>
          Review the details. If a repository can't be read, its saved copies
          are kept. Check its branch and GitHub access before syncing again.
        </p>
      ) : (
        <p>Build your profile to include new or updated project evidence.</p>
      )}
      {failures.length || warnings.length ? (
        <ul className="space-y-1 text-muted-foreground [overflow-wrap:anywhere]">
          {failures.map(([repo, reason]) => (
            <li key={repo}>
              {repo}: {githubSyncFailureLabel(reason, i18n.resolvedLanguage)}
            </li>
          ))}
          {warnings.map((warning) => (
            <li key={warning}>{profileBuildReportLineLabel(t, "warning", warning, i18n.resolvedLanguage)}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
