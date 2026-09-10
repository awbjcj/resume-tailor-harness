import { useTranslation } from "react-i18next";
import { Progress } from "@/components/ui/progress";
import { localizeRunKind, localizeRunPhase } from "@/i18n/dynamic-labels";
import { useRunStore } from "@/lib/runs/store";
import { OperationHistory } from "./OperationHistory";

export function RecentRuns() {
  const { t, i18n } = useTranslation();
  const runsMap = useRunStore((s) => s.runs);
  const runs = Object.values(runsMap)
    .filter((run) => ["running", "cancelling", "queued"].includes(run.status))
    .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  return (
    <OperationHistory activeRuns={runs.length === 0 ? null : (
      <ul className="flex flex-col gap-3">
        {runs.map((run) => {
          const kind = localizeRunKind(run.kind, i18n.resolvedLanguage, t);
          const phase = localizeRunPhase(run.phase, i18n.resolvedLanguage);
          return <li key={run.runId} className="min-w-0">
            <div className="flex items-baseline justify-between gap-3 text-xs font-semibold">
              <span className="truncate">{kind}{phase ? ` · ${phase}` : ""}</span>
              <span className="shrink-0 text-muted-foreground tabular-nums">
                {run.status === "running" ? `${Math.round(run.percent)}%` : t(`runHistory.outcomes.${run.status}`)}
              </span>
            </div>
            <Progress value={Math.round(run.percent)} aria-label={t("dashboard.runProgress", { kind })}
              className="mt-1.5 h-1.5" />
          </li>;
        })}
      </ul>
    )} />
  );
}
