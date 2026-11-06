import { useId, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, unwrap } from "@/lib/api/client";
import { formatUserDateTime, formatUserTime } from "@/lib/date-time";
import { localizeRunError, localizeRunKind, localizeRunLogMessage, localizeRunPhase } from "@/i18n/dynamic-labels";
import { ClearHistoryButton } from "@/features/notifications/ClearHistoryButton";
import { RunResultLink } from "@/features/runs/RunResultLink";
import { useClearOperationHistory, useRunCompletions, type RunCompletionItem } from "@/features/notifications/use-run-completions";

function Operation({ item }: { item: RunCompletionItem }) {
  const { t, i18n } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const logs = useQuery({
    queryKey: ["operation-logs", item.id],
    enabled: expanded,
    queryFn: () => unwrap(api.GET("/api/run-completions/{completion_id}/logs", {
      params: { path: { completion_id: item.id } },
    })),
  });
  const kind = localizeRunKind(item.kind, i18n.resolvedLanguage, t);
  return <li className="min-w-0 px-3 py-2.5">
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="min-w-0 flex-1 basis-48">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="wrap-anywhere text-sm font-medium">{kind} · {t(`runHistory.outcomes.${item.status}`)}</span>
          <time className="text-xs text-muted-foreground" dateTime={item.completedAt}>
            {formatUserDateTime(item.completedAt, i18n.resolvedLanguage)}
          </time>
        </div>
        {item.label && <p className="mt-1 wrap-anywhere text-sm text-muted-foreground">{localizeRunPhase(item.label, i18n.resolvedLanguage)}</p>}
        {item.error && <p className="mt-1 wrap-anywhere text-sm text-destructive">{localizeRunError(item.error, i18n.resolvedLanguage)}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <RunResultLink item={item} />
        <Button size="xs" variant="ghost" aria-expanded={expanded}
          aria-controls={`operation-logs-${item.id}`} onClick={() => setExpanded(!expanded)}>
          {t(expanded ? "runHistory.hideLogs" : "runHistory.viewLogs")}
        </Button>
      </div>
    </div>
    {expanded && <div id={`operation-logs-${item.id}`} className="mt-3 max-h-64 overflow-y-auto border-t pt-3 text-xs">
      {logs.isPending ? <p role="status">{t("runHistory.loadingLogs")}</p>
        : logs.isError ? <p role="alert">{t("runHistory.logsError")} <Button size="xs" variant="ghost" onClick={() => void logs.refetch()}>{t("runHistory.retry")}</Button></p>
        : !logs.data?.length ? <p>{t("runHistory.noLogs")}</p>
        : <ol className="space-y-2">{logs.data.map((entry, index) => <li key={index} className="wrap-anywhere">
          <time className="mr-2 text-muted-foreground" dateTime={entry.timestamp}>{formatUserTime(entry.timestamp, i18n.resolvedLanguage)}</time>
          {localizeRunLogMessage(entry.message, i18n.resolvedLanguage)}
        </li>)}</ol>}
    </div>}
  </li>;
}

export function OperationHistory({ activeRuns }: { activeRuns?: ReactNode }) {
  const { t } = useTranslation();
  const headingId = useId();
  const history = useRunCompletions("operations");
  const clear = useClearOperationHistory();
  return (
    <section aria-labelledby={headingId}>
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle><h2 id={headingId}>{t("dashboard.recentRuns")}</h2></CardTitle>
          <ClearHistoryButton label={t("runHistory.clearOperations")} pending={clear.isPending}
            disabled={!history.data?.length} error={clear.error}
            onClear={(onSuccess) => clear.mutate(undefined, { onSuccess })} />
        </CardHeader>
        <CardContent className="space-y-3">
          {activeRuns}
          {history.isPending ? <p role="status">{t("runHistory.loadingHistory")}</p>
            : history.isError ? <p role="alert">{t("runHistory.historyError")} <Button size="xs" variant="ghost" onClick={() => void history.refetch()}>{t("runHistory.retry")}</Button></p>
            : !history.data.length ? <p className="text-sm text-muted-foreground">{t("runHistory.emptyHistory")}</p>
            : <ul className="max-h-[36rem] divide-y overflow-y-auto rounded-lg border">{history.data.map((item) => <Operation key={item.id} item={item} />)}</ul>}
        </CardContent>
      </Card>
    </section>
  );
}
