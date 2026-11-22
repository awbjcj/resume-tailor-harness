import i18n from "i18next";

export const notificationsCopyEn = {
  aria: "Notifications",
  ariaPending: "Notifications ({{count}} pending)",
  loading: "Loading notifications…",
  loadError: "Could not load notifications.",
  nothingPending: "Nothing pending.",
  runHistory: "Run history",
  markAllRead: "Mark all read",
  applicationNotifications: "Application notifications",
  needsReview: "Needs your review",
  reminders: "Upcoming reminders",
  noApplicationNotifications: "No pending application updates or reminders.",
  syncGmail: "Sync Gmail",
  syncingGmail: "Syncing Gmail…",
  gmailSettingsHelp: "Sync recruiting emails and review suggested updates under Application notifications on the dashboard.",
  approve: "Approve",
  reject: "Reject update",
  dismiss: "Dismiss",
  viewJob: "View job",
  draftFollowUp: "Draft follow-up",
  acknowledge: "Acknowledge",
  acknowledged: "Reminder acknowledged.",
  approved: "Application update approved.",
  rejected: "Application update rejected.",
  dismissed: "Reminder dismissed.",
  savingDecision: "Saving decision…",
  decisionError: "Could not save your decision. Try again.",
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
