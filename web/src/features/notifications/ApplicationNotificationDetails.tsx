import "@/i18n/interaction-copy-notifications";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { buttonVariants } from "@/components/ui/button";
import { notificationEvidence } from "./notification-evidence";
import type { NotificationItem } from "./use-notifications";

function notificationTitle(t: TFunction, item: NotificationItem) {
  const company = item.company || t("interactionCopy.notifications.application");
  if (item.kind === "follow_up") return t("interactionCopy.notifications.followUp", { company });
  if (item.kind === "interview_soon") return t("interactionCopy.notifications.interviewSoon", { company });
  if (item.kind === "offer_deadline_soon") return t("interactionCopy.notifications.offerDeadline", { company });
  if (!item.proposedStatus) return t("interactionCopy.notifications.applicationUpdate");
  const knownStatus = /^(ready|submitted|interview|offer|rejected|closed)$/.test(item.proposedStatus);
  const status = knownStatus
    ? t(`application.statuses.${item.proposedStatus}` as "application.statuses.ready")
    : item.proposedStatus;
  return t("interactionCopy.notifications.moveTo", { status });
}

export function ApplicationNotificationDetails({ item }: { item: NotificationItem }) {
  const { t, i18n } = useTranslation();
  const job = [item.company, item.title].filter(Boolean).join(" · ");
  return (
    <div className="min-w-0 flex-1 wrap-anywhere">
      <p className="font-medium">{notificationTitle(t, item)}</p>
      {item.proposedStatus && job && <p className="mt-0.5 text-sm text-muted-foreground">{job}</p>}
      <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
        {notificationEvidence(t, i18n.resolvedLanguage, item.kind, item.evidence)}
      </p>
    </div>
  );
}

export function NotificationJobLink({ jobId, className }: { jobId: number; className?: string }) {
  const { t } = useTranslation();
  return (
    <Link to={`/pipeline?job=${jobId}`} className={buttonVariants({ variant: "outline", size: "sm", className })}>
      {t("interactionCopy.notifications.viewJob")}
    </Link>
  );
}
