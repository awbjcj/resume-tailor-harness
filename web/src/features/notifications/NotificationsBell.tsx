import "@/i18n/interaction-copy-notifications";
import { Bell, CircleCheck, Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { RunResultLink } from "@/features/runs/RunResultLink";
import { localizeRunError, localizeRunKind, localizeRunPhase } from "@/i18n/dynamic-labels";
import { formatUserDateTime } from "@/lib/date-time";

import { ApplicationNotificationDetails, NotificationJobLink } from "./ApplicationNotificationDetails";
import { ClearHistoryButton } from "./ClearHistoryButton";
import { isEventReminder } from "./notification-evidence";
import { useClearNotificationHistory, useNotifications } from "./use-notifications";
import { useMarkAllRunCompletionsRead, useMarkRunCompletionRead, useRunCompletions } from "./use-run-completions";

export function NotificationsBell() {
  const { t, i18n } = useTranslation();
  const notifications = useNotifications();
  const runs = useRunCompletions();
  const markRunRead = useMarkRunCompletionRead();
  const markAllRunsRead = useMarkAllRunCompletionsRead();
  const clear = useClearNotificationHistory();

  const reminders = notifications.data?.filter(isEventReminder) ?? [];
  const runItems = runs.data ?? [];
  const unreadRuns = runItems.filter((item) => item.readAt == null).length;
  const count = reminders.length + unreadRuns;
  const loading = notifications.isPending || runs.isPending;
  const failed = notifications.isError || runs.isError;

  return (
    <Popover>
      <PopoverTrigger render={
        <Button variant="ghost" size="icon" className="relative"
          aria-label={count ? t("interactionCopy.notifications.ariaPending", { count }) : t("interactionCopy.notifications.aria")}>
          <Bell className="size-4" aria-hidden="true" />
          {count > 0 && (
            <span aria-hidden="true" className="absolute -right-0.5 -top-0.5 flex min-w-5 items-center justify-center rounded-full bg-primary px-1 text-[0.68rem] font-semibold leading-5 text-primary-foreground">
              {count}
            </span>
          )}
        </Button>
      } />
      <PopoverContent align="end" className="w-[min(24rem,calc(100vw-2rem))] gap-3 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <PopoverTitle>{t("interactionCopy.notifications.aria")}</PopoverTitle>
          <ClearHistoryButton label={t("runHistory.clearNotifications")} pending={clear.isPending}
            disabled={runItems.length === 0} error={clear.error}
            onClear={(onSuccess) => clear.mutate(undefined, { onSuccess })} />
        </div>
        {failed && (
          <div className="flex flex-wrap items-center gap-2">
            <p role="alert" className="text-destructive">{t("interactionCopy.notifications.loadError")}</p>
            <Button size="xs" variant="outline" onClick={() => {
              if (notifications.isError) void notifications.refetch();
              if (runs.isError) void runs.refetch();
            }}>{t("runHistory.retry")}</Button>
          </div>
        )}
        {loading && <p role="status" className="text-muted-foreground">{t("interactionCopy.notifications.loading")}</p>}
        {!loading && !failed && reminders.length === 0 && runItems.length === 0 && (
          <p className="flex items-center gap-2 rounded-lg border border-dashed bg-muted/20 p-3 text-muted-foreground">
            <Inbox className="size-4" aria-hidden="true" />
            {t("interactionCopy.notifications.nothingPending")}
          </p>
        )}
        <div className="max-h-[min(28rem,55dvh)] space-y-4 overflow-y-auto p-1 empty:hidden">
          {reminders.length > 0 && (
            <section aria-labelledby="bell-reminders">
              <h3 id="bell-reminders" className="mb-2 text-xs font-semibold text-muted-foreground">
                {t("interactionCopy.notifications.reminders")}
              </h3>
              <ul className="space-y-2">
                {reminders.map((item) => (
                  <li key={item.id} className="space-y-2 rounded-lg border p-3">
                    <ApplicationNotificationDetails item={item} />
                    {item.jobId != null && <NotificationJobLink jobId={item.jobId} />}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {runItems.length > 0 && (
            <section aria-labelledby="bell-run-history">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 id="bell-run-history" className="text-xs font-semibold text-muted-foreground">
                  {t("interactionCopy.notifications.runHistory")}
                </h3>
                {unreadRuns > 0 && (
                  <Button type="button" size="xs" variant="ghost" disabled={markAllRunsRead.isPending}
                    onClick={() => markAllRunsRead.mutate()}>
                    {t("interactionCopy.notifications.markAllRead")}
                  </Button>
                )}
              </div>
              <ul className="space-y-2">
                {runItems.map((item) => {
                  const kind = localizeRunKind(item.kind, i18n.resolvedLanguage, t);
                  const status = t(`runHistory.outcomes.${item.status}`);
                  const hasSyncDetail = item.kind === "gmailSync"
                    && (item.label === "Done with warnings" || item.label === "Sync complete; more emails remain");
                  return (
                    <li key={item.id} className={`flex items-start justify-between gap-2 rounded-lg border p-3 ${item.readAt == null ? "bg-primary/5" : "bg-background"}`}>
                      <div className="min-w-0 wrap-anywhere">
                        <p className="font-medium">{t("interactionCopy.notifications.runStatus", { kind, status })}</p>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">
                          {localizeRunError(item.error, i18n.resolvedLanguage) ?? (hasSyncDetail
                            ? localizeRunPhase(item.label, i18n.resolvedLanguage)
                            : formatUserDateTime(item.completedAt, i18n.resolvedLanguage))}
                        </p>
                        <div className="mt-2 empty:hidden"><RunResultLink item={item} /></div>
                      </div>
                      {item.readAt == null && (
                        <Button type="button" size="icon-sm" variant="ghost"
                          aria-label={t("runHistory.markRead", { kind })} disabled={markRunRead.isPending}
                          onClick={() => markRunRead.mutate(item.id)}>
                          <CircleCheck aria-hidden="true" />
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
