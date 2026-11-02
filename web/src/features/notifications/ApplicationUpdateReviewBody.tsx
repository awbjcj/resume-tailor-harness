import { useTranslation } from "react-i18next";

import { EventFormDialog } from "@/features/job/EventFormDialog";
import { ApiError } from "@/lib/api/client";
import { useAcceptNotification, type NotificationItem } from "./use-notifications";

const INTERVIEW_KIND_VALUES = [
  "recruiter_screen", "online_assessment", "questionnaire", "technical_phone_screen",
  "technical_round", "system_design", "behavioral", "hiring_manager", "onsite_loop", "team_match",
];
const STATUS_KINDS: Record<string, string[]> = {
  submitted: ["application_submitted"],
  interview: INTERVIEW_KIND_VALUES,
  offer: ["offer_received", "offer_deadline"],
  rejected: ["rejected"],
  closed: ["withdrawn"],
};

export function ApplicationUpdateReviewBody({
  item: reviewed,
  onClose,
}: {
  item: NotificationItem;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const accept = useAcceptNotification();

  return (
    <EventFormDialog
      open
      onOpenChange={(open) => !open && onClose()}
      initialValues={{
        // An interview status alone does not identify the interview stage.
        kind: reviewed.proposedStatus === "interview" ? "" : STATUS_KINDS[reviewed.proposedStatus][0],
        notes: reviewed.evidence,
        allDay: true,
      }}
      review={{
        title: t("applicationUpdates.reviewTitle"),
        description: t("applicationUpdates.reviewDescription"),
        submitLabel: t("applicationUpdates.acceptAndAdd"),
        confirmationLabel: t("applicationUpdates.confirmDetails"),
        allowedKinds: STATUS_KINDS[reviewed.proposedStatus],
        context: (
          <div className="space-y-2 rounded-lg border bg-muted/20 p-3 text-sm">
            <p className="font-medium">{reviewed.company} · {reviewed.title}</p>
            <p>{t("applicationUpdates.proposedStatus", {
              status: t(`application.statuses.${reviewed.proposedStatus}`, {
                defaultValue: reviewed.proposedStatus,
              }),
            })}</p>
            <p className="text-xs font-medium text-muted-foreground">{t("applicationUpdates.evidence")}</p>
            <p className="whitespace-pre-wrap text-sm">{reviewed.evidence}</p>
          </div>
        ),
      }}
      onSubmit={async (event) => {
        try {
          await accept.mutateAsync({
            id: reviewed.id,
            event,
            expectedRevision: reviewed.revision,
            eventDetailsConfirmed: true,
          });
        } catch (error) {
          if (error instanceof ApiError && ["NOTIFICATION_CHANGED", "NOT_FOUND"].includes(error.code)) {
            throw new Error(t("applicationUpdates.changed"), { cause: error });
          }
          throw error;
        }
      }}
    />
  );
}
