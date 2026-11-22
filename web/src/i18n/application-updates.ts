import i18n from "i18next";

export const applicationUpdatesEn = {
  addToTimeline: "Add to timeline",
  reviewTitle: "Review application update",
  reviewDescription: "Accept this status update and add a confirmed event to the timeline.",
  proposedStatus: "Proposed status: {{status}}",
  evidence: "Message evidence",
  confirmDetails: "I've confirmed the stage and date, as well as the time and time zone if applicable, from the message or with the employer.",
  dateHelp: "Enter the event date. The time you received the message doesn't confirm an interview appointment.",
  confirmRequired: "Confirm the event details before accepting this update.",
  chooseStage: "Choose a stage",
  stageRequired: "Choose the stage described in the message.",
  timeRequired: "Enter the confirmed time and time zone, or choose All day if the event has only a date.",
  acceptAndAdd: "Accept and add event",
  changed: "This update has changed. Close this draft and review the latest application update.",
};

export const applicationUpdatesZh: typeof applicationUpdatesEn = {
  addToTimeline: "添加到时间线",
  reviewTitle: "审核申请状态更新",
  reviewDescription: "接受此状态更新，并将已确认的事件添加到时间线。",
  proposedStatus: "建议状态：{{status}}",
  evidence: "邮件依据",
  confirmDetails: "我已通过邮件或向雇主核实事件阶段和日期，以及适用的时间和时区。",
  dateHelp: "请输入事件日期。收到邮件的时间不能作为面试预约的依据。",
  confirmRequired: "请先确认事件详情，再接受此更新。",
  chooseStage: "请选择阶段",
  stageRequired: "请选择邮件中描述的阶段。",
  timeRequired: "请输入已确认的时间和时区；如果事件只有日期，请选择“全天”。",
  acceptAndAdd: "接受并添加事件",
  changed: "此更新已有变化。请关闭草稿，重新审核最新的申请更新。",
};

function register() {
  i18n.addResourceBundle("en", "translation", { applicationUpdates: applicationUpdatesEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { applicationUpdates: applicationUpdatesZh }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
