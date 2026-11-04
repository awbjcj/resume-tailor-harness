import i18n from "i18next";

export const notificationsCopyEn = {
  aria: "Notifications",
  ariaPending: "Notifications ({{count}} pending)",
  runStatus: "{{kind}} {{status}}",
  application: "application",
  followUp: "Follow up: {{company}}",
  interviewSoon: "Interview soon: {{company}}",
  offerDeadline: "Offer deadline: {{company}}",
  moveTo: "Move to {{status}}",
  noActivity_one: "No activity for {{count}} day: {{subject}}",
  noActivity_other: "No activity for {{count}} days: {{subject}}",
  eventEvidence: "{{label}} {{time}}: {{subject}}",
  interview: "Interview",
  deadline: "Offer deadline",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { notifications: notificationsCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
