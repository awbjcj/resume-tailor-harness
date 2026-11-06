import { Activity, DatabaseZap, TrendingDown, TrendingUp } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";

import type { DashboardSummary } from "./use-dashboard-summary";

function score(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(1)} / 5`;
}

export function InsightsCard({ summary }: { summary: DashboardSummary }) {
  const { t } = useTranslation();
  const practice = summary.practiceStats;
  const sources = summary.sourceHealth;
  const affectedSources = sources?.affectedSources ?? [];
  const change = practice?.changeFromFirst;
  const TrendIcon = change != null && change < 0 ? TrendingDown : TrendingUp;
  const showPractice = (practice?.completedSessions ?? 0) > 0;
  if (!showPractice && !sources) return null;

  return (
    <Card>
      <CardContent className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,18rem),1fr))] gap-6">
        {showPractice ? <section aria-labelledby="practice-insight-title" className="min-w-0">
          <div className="flex items-center gap-2 text-primary">
            <Activity className="size-4" aria-hidden="true" />
            <h2 id="practice-insight-title" className="text-sm font-semibold">
              {t("dashboard.practice")}
            </h2>
          </div>
          <div className="mt-3 flex items-end justify-between gap-3">
            <div>
              <p className="text-2xl font-semibold tabular-nums">{score(practice?.averageScore)}</p>
              <p className="text-xs text-muted-foreground">{t("dashboard.averageScore")}</p>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <p>{t("dashboard.completedSessions", { count: practice?.completedSessions ?? 0 })}</p>
              {change != null && (
                <p className="mt-1 inline-flex items-center gap-1 font-medium text-foreground">
                  <TrendIcon className="size-3" aria-hidden="true" />
                  {change > 0 ? "+" : ""}{change.toFixed(1)} {t("dashboard.sinceFirst")}
                </p>
              )}
            </div>
          </div>
        </section> : null}

        {sources ? <section aria-labelledby="source-insight-title" className="min-w-0">
          <div className="flex items-center gap-2 text-primary">
            <DatabaseZap className="size-4" aria-hidden="true" />
            <h2 id="source-insight-title" className="text-sm font-semibold">
              {t("dashboard.sourceHealth")}
            </h2>
          </div>
          {sources?.openFailures ? (
            <div className="mt-3">
              <p className="text-2xl font-semibold tabular-nums">{affectedSources.length}</p>
              <p className="text-xs text-muted-foreground">
                {t(
                  affectedSources.length === 1
                    ? "dashboard.sourcesNeedAttention_one"
                    : "dashboard.sourcesNeedAttention_other",
                  { count: affectedSources.length },
                )}
              </p>
              <p className="mt-2 truncate text-xs font-medium" title={affectedSources.join(", ")}>
                {affectedSources.join(" · ")}
              </p>
            </div>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">{t("dashboard.sourcesHealthy")}</p>
          )}
        </section> : null}
      </CardContent>
    </Card>
  );
}
