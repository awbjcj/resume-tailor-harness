import type { TFunction } from "i18next";

// These reminders are produced by the app in a fixed format. Email excerpts
// and any unrecognized messages must stay exactly as received.
export function notificationEvidence(t: TFunction, language: string | undefined, kind: string, evidence: string): string {
  const followUp = kind === "follow_up" && /^No activity for (\d+) days: ([\s\S]+)$/.exec(evidence);
  if (followUp) {
    return t("interactionCopy.notifications.noActivity", { count: Number(followUp[1]), subject: followUp[2] });
  }
  if (!language?.startsWith("zh") || (kind !== "interview_soon" && kind !== "offer_deadline_soon")) return evidence;

  const event = /^(Interview|Offer deadline) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{2}), (\d{2}:\d{2} UTC): ([\s\S]+)$/.exec(evidence);
  if (!event) return evidence;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const label = t(event[1] === "Interview" ? "interactionCopy.notifications.interview" : "interactionCopy.notifications.deadline");
  return t("interactionCopy.notifications.eventEvidence", {
    label,
    time: `${months.indexOf(event[2]) + 1}月${Number(event[3])}日 ${event[4]}`,
    subject: event[5],
  });
}
