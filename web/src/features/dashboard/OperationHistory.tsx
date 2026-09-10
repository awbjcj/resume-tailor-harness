import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, unwrap } from "@/lib/api/client";
import { localizeRunError, localizeRunKind, localizeRunPhase } from "@/i18n/dynamic-labels";
import { ClearHistoryButton } from "@/features/notifications/ClearHistoryButton";
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
  return <li className="min-w-0 rounded-lg border p-3">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="text-sm font-medium">{kind} · {t(`runHistory.outcomes.${item.status}`)}</div>
        <time className="text-xs text-muted-foreground" dateTime={item.completedAt}>
          {new Date(item.completedAt).toLocaleString(i18n.resolvedLanguage)}
        </time>
      </div>
      <Button size="xs" variant="ghost" aria-expanded={expanded}
        aria-controls={`operation-logs-${item.id}`} onClick={() => setExpanded(!expanded)}>
        {t(expanded ? "runHistory.hideLogs" : "runHistory.viewLogs")}
      </Button>
    </div>
    {item.label && <p className="mt-1 break-words text-sm text-muted-foreground">{localizeRunPhase(item.label, i18n.resolvedLanguage)}</p>}
    {item.error && <p className="mt-1 break-words text-sm text-destructive">{localizeRunError(item.error, i18n.resolvedLanguage)}</p>}
    {expanded && <div id={`operation-logs-${item.id}`} className="mt-3 max-h-64 overflow-y-auto border-t pt-3 text-xs">
      {logs.isPending ? <p role="status">{t("runHistory.loadingLogs")}</p>
        : logs.isError ? <p role="alert">{t("runHistory.logsError")} <Button size="xs" variant="ghost" onClick={() => void logs.refetch()}>{t("runHistory.retry")}</Button></p>
        : !logs.data?.length ? <p>{t("runHistory.noLogs")}</p>
        : <ol className="space-y-2">{logs.data.map((entry, index) => <li key={index} className="break-words">
          <time className="mr-2 text-muted-foreground" dateTime={entry.timestamp}>{new Date(entry.timestamp).toLocaleTimeString(i18n.resolvedLanguage)}</time>
          {localizeRunError(entry.message, i18n.resolvedLanguage)}
        </li>)}</ol>}
    </div>}
  </li>;
}

export function OperationHistory({ activeRuns }: { activeRuns?: ReactNode }) {
  const { t } = useTranslation();
  const history = useRunCompletions("operations");
  const clear = useClearOperationHistory();
  return <Card>
    <CardHeader className="flex flex-wrap items-start justify-between gap-3">
      <div><CardTitle>{t("dashboard.recentRuns")}</CardTitle>
        <p className="mt-1 text-xs text-muted-foreground">{t("runHistory.historyHint")}</p></div>
      <ClearHistoryButton label={t("runHistory.clearOperations")} pending={clear.isPending}
        disabled={!history.data?.length} error={clear.error}
        onClear={(onSuccess) => clear.mutate(undefined, { onSuccess })} />
    </CardHeader>
    <CardContent className="space-y-3">
      {activeRuns}
      {history.isPending ? <p role="status">{t("runHistory.loadingHistory")}</p>
        : history.isError ? <p role="alert">{t("runHistory.historyError")} <Button size="xs" variant="ghost" onClick={() => void history.refetch()}>{t("runHistory.retry")}</Button></p>
        : !history.data.length ? <p className="text-sm text-muted-foreground">{t("runHistory.emptyHistory")}</p>
        : <ul className="max-h-[36rem] space-y-3 overflow-y-auto">{history.data.map((item) => <Operation key={item.id} item={item} />)}</ul>}
    </CardContent>
  </Card>;
}
