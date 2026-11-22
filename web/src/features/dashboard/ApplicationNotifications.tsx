import { useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { EmailDraftDialog } from "@/features/job/EmailDraftDialog";
import { ApplicationNotificationDetails, NotificationJobLink } from "@/features/notifications/ApplicationNotificationDetails";
import { ApplicationUpdateReviewDialog } from "@/features/notifications/ApplicationUpdateReviewDialog";
import { isEventReminder } from "@/features/notifications/notification-evidence";
import {
  useAcceptNotification,
  useDismissNotification,
  useGmailSync,
  useNotifications,
  type NotificationItem,
} from "@/features/notifications/use-notifications";
import { localizeRunError } from "@/i18n/dynamic-labels";

type DecisionFeedback =
  | { status: "approved" | "rejected" | "acknowledged" | "dismissed" }
  | { status: "failed"; itemId: number };

export function ApplicationNotifications() {
  const { t, i18n } = useTranslation();
  const notifications = useNotifications();
  const accept = useAcceptNotification();
  const dismiss = useDismissNotification();
  const sync = useGmailSync();
  const heading = useRef<HTMLHeadingElement>(null);
  const [draftJobId, setDraftJobId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<DecisionFeedback | null>(null);

  const items = notifications.data ?? [];
  const groups = [
    { title: "interactionCopy.notifications.needsReview", items: items.filter((item) => !isEventReminder(item)) },
    { title: "interactionCopy.notifications.reminders", items: items.filter(isEventReminder) },
  ] as const;
  const saving = accept.isPending || dismiss.isPending;

  async function decide(item: NotificationItem, approve: boolean, trigger: HTMLElement) {
    setFeedback(null);
    const draft = approve && item.kind === "follow_up" ? item.jobId : null;
    try {
      await (approve ? accept : dismiss).mutateAsync(item.id);
      if (draft != null) {
        setDraftJobId(draft);
      } else if (item.proposedStatus) {
        setFeedback({ status: approve ? "approved" : "rejected" });
      } else {
        setFeedback({ status: approve ? "acknowledged" : "dismissed" });
      }
      if (document.activeElement === document.body || document.activeElement === trigger) {
        heading.current?.focus({ preventScroll: true });
      }
    } catch {
      setFeedback({ status: "failed", itemId: item.id });
    }
  }

  return (
    <section aria-labelledby="application-notifications" className="min-w-0">
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <CardTitle>
            <h2 id="application-notifications" tabIndex={-1} ref={heading} className="scroll-mt-24 focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
              {t("interactionCopy.notifications.applicationNotifications")}
            </h2>
          </CardTitle>
          <CardAction className="mt-0 flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="min-h-11 sm:min-h-9"
              disabled={sync.isPending} onClick={() => sync.mutate()}>
              <RefreshCw className={sync.isPending ? "motion-safe:animate-spin" : undefined} aria-hidden="true" />
              {t("interactionCopy.notifications.syncGmail")}
            </Button>
            <Button size="sm" variant="ghost" className="min-h-11 sm:min-h-9"
              disabled={sync.isPending} onClick={() => sync.mutate({ reviewCleared: true })}>
              {t("runHistory.reviewClearedGmail")}
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {sync.isPending && <p role="status" className="sr-only">{t("interactionCopy.notifications.syncingGmail")}</p>}
          {sync.error && <p role="alert" className="text-destructive">
            {localizeRunError(sync.error.message, i18n.resolvedLanguage)}
          </p>}
          <p role="status" className="sr-only">
            {saving ? t("interactionCopy.notifications.savingDecision")
              : feedback && feedback.status !== "failed" ? t(`interactionCopy.notifications.${feedback.status}`) : ""}
          </p>
          {notifications.isError && (
            <div className="flex flex-wrap items-center gap-2">
              <p role="alert" className="text-destructive">{t("interactionCopy.notifications.loadError")}</p>
              <Button size="sm" variant="outline" className="min-h-11 sm:min-h-9" onClick={() => void notifications.refetch()}>
                {t("runHistory.retry")}
              </Button>
            </div>
          )}
          {notifications.isPending ? (
            <p role="status" className="text-muted-foreground">{t("interactionCopy.notifications.loading")}</p>
          ) : !notifications.isError && items.length === 0 && (
            <p className="text-muted-foreground">{t("interactionCopy.notifications.noApplicationNotifications")}</p>
          )}
          {groups.map((group) => group.items.length > 0 && (
            <div key={group.title} className="space-y-2">
              <h3 className="text-sm font-semibold">{t(group.title)}</h3>
              <ul className="divide-y rounded-lg border border-border">
                {group.items.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-start gap-3 p-3 sm:p-4">
                    <div className="min-w-0 grow basis-64">
                      <ApplicationNotificationDetails item={item} />
                    </div>
                    <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto [&_button]:min-h-11 sm:[&_button]:min-h-9">
                      <Button size="sm" variant="ghost" disabled={saving} focusableWhenDisabled
                        onClick={(event) => void decide(item, false, event.currentTarget)}>
                        {dismiss.isPending && dismiss.variables === item.id && <Spinner aria-hidden="true" />}
                        {t(item.proposedStatus ? "interactionCopy.notifications.reject" : "interactionCopy.notifications.dismiss")}
                      </Button>
                      {item.proposedStatus && <ApplicationUpdateReviewDialog item={item} disabled={saving} />}
                      {isEventReminder(item) ? (
                        item.jobId != null && <NotificationJobLink jobId={item.jobId} className="min-h-11 sm:min-h-9" />
                      ) : (
                        <Button size="sm" className={item.proposedStatus ? "max-sm:grow" : undefined}
                          disabled={saving} focusableWhenDisabled onClick={(event) => void decide(item, true, event.currentTarget)}>
                          {accept.isPending && accept.variables === item.id && <Spinner aria-hidden="true" />}
                          {t(item.kind === "follow_up" && item.jobId != null
                            ? "interactionCopy.notifications.draftFollowUp"
                            : item.proposedStatus ? "interactionCopy.notifications.approve" : "interactionCopy.notifications.acknowledge")}
                        </Button>
                      )}
                    </div>
                    {feedback?.status === "failed" && feedback.itemId === item.id && (
                      <p role="alert" className="basis-full text-destructive">{t("interactionCopy.notifications.decisionError")}</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </CardContent>
      </Card>
      {draftJobId != null && (
        <EmailDraftDialog jobId={draftJobId} defaultType="follow_up" open
          onOpenChange={(open) => !open && setDraftJobId(null)} />
      )}
    </section>
  );
}
