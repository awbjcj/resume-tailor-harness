import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { useProfileOperation } from "./use-profile-operation";
import { localizeRunError, localizeRunPhase } from "@/i18n/dynamic-labels";

import {
  profileBuildReportLineLabel,
  profileBuildStatusLabel,
} from "@/i18n/profile-build-diagnostics";

type BuildReport = {
  experiences?: number;
  projects?: number;
  docStatus?: Record<string, string>;
  anchorDecisions?: string[];
  verificationDrops?: string[];
  conflicts?: string[];
  warnings?: string[];
};

function Section({
  title,
  lines,
  tone,
}: {
  title: string;
  lines: string[];
  tone?: "warn";
}) {
  if (lines.length === 0) return null;
  return (
    <div>
      <div className="text-xs font-medium uppercase text-muted-foreground">
        {title}
      </div>
      <ul
        className={`mt-1 flex flex-col gap-0.5 text-sm ${tone === "warn" ? "text-destructive" : ""}`}
      >
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </div>
  );
}

export function BuildReportPanel() {
  const { t, i18n } = useTranslation();
  const latest = useProfileOperation("profile-build");
  if (!latest) return null;
  if (["queued", "running", "cancelling"].includes(latest.status))
    return (
      <section
        aria-label="Profile build progress"
        className="space-y-3 rounded-xl border border-border bg-card p-4 sm:p-5"
      >
        <h2 className="flex items-center gap-2 font-semibold">
          <Spinner />
          Building profile
        </h2>
        <p role="status" className="text-sm text-muted-foreground">
          {localizeRunPhase(latest.phase, i18n.resolvedLanguage)}
        </p>
        <Progress
          value={Math.round(latest.percent)}
          aria-label="Profile build progress"
        />
      </section>
    );
  if (latest.status === "failed" || latest.status === "cancelled")
    return (
      <section
        role={latest.status === "failed" ? "alert" : "status"}
        className="space-y-2 rounded-xl border border-border bg-card p-4 sm:p-5"
      >
        <h2 className="font-semibold">
          {latest.status === "failed"
            ? "Profile build failed"
            : "Profile build cancelled"}
        </h2>
        {latest.error ? (
          <p className="text-sm text-destructive [overflow-wrap:anywhere]">
            {localizeRunError(latest.error, i18n.resolvedLanguage)}
          </p>
        ) : null}
        <p className="text-sm text-muted-foreground">
          Your saved sources are available. Resolve the issue and build your
          profile again.
        </p>
      </section>
    );
  if (!latest?.result) return null;
  const report = latest.result as BuildReport;
  const docStatus = Object.entries(report.docStatus ?? {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([doc, status]) => `${doc}: ${profileBuildStatusLabel(t, status)}`);

  return (
    <section
      aria-label="Profile build report"
      className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 sm:p-5"
    >
      <h2 className="flex items-center gap-2 font-semibold">
        <CheckCircle2 className="size-5 text-primary" aria-hidden="true" />
        Profile ready
      </h2>
      <div className="text-sm font-medium">
        Last build: {report.experiences ?? 0} experiences,{" "}
        {report.projects ?? 0} projects
      </div>
      <details className="rounded-lg border border-border px-4">
        <summary className="min-h-11 cursor-pointer py-3 text-sm font-medium">
          Source diagnostics
        </summary>
        <div className="space-y-3 pb-4 [overflow-wrap:anywhere]">
          <Section title="Document status" lines={docStatus} />
          <Section
            title="Anchor decisions"
            lines={(report.anchorDecisions ?? []).map((line) =>
              profileBuildReportLineLabel(t, "anchor", line),
            )}
          />
          <Section
            title="Dropped claims"
            lines={(report.verificationDrops ?? []).map((line) =>
              profileBuildReportLineLabel(t, "verificationDrop", line),
            )}
            tone="warn"
          />
          <Section
            title="Conflicts"
            lines={(report.conflicts ?? []).map((line) =>
              profileBuildReportLineLabel(t, "conflict", line),
            )}
          />
        </div>
      </details>
      <Section
        title="Warnings"
        lines={(report.warnings ?? []).map((line) =>
          profileBuildReportLineLabel(t, "warning", line, i18n.resolvedLanguage),
        )}
        tone="warn"
      />
    </section>
  );
}
