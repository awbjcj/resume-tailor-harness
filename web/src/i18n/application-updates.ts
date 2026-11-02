import i18n from "i18next";

export const applicationUpdatesEn = {
  addToTimeline: "Add to timeline",
  reviewTitle: "Review application update",
  reviewDescription: "Accept this status update and save a confirmed timeline event together.",
  proposedStatus: "Proposed status: {{status}}",
  evidence: "Message evidence",
  confirmDetails: "I confirmed the stage, date, and any time and timezone from the message or with the employer.",
  dateHelp: "Enter the event date. The message receipt time does not establish an interview appointment.",
  confirmRequired: "Confirm the event details before accepting this update.",
  chooseStage: "Choose a stage",
  stageRequired: "Choose the stage described in the message.",
  timeRequired: "Enter the confirmed time and timezone, or select All day for a date-only event.",
  acceptAndAdd: "Accept and add event",
  changed: "This update changed. Close this draft and review the latest application update.",
};

export const applicationUpdatesZh = {
  addToTimeline: "添加到时间线",
  reviewTitle: "审核申请状态更新",
  reviewDescription: "同时接受状态更新并保存已确认的时间线事件。",
  proposedStatus: "建议状态：{{status}}",
  evidence: "邮件依据",
  confirmDetails: "我已根据邮件或与雇主核实，确认事件阶段、日期及适用的时间和时区。",
  dateHelp: "请输入事件日期。邮件接收时间不能作为面试预约时间。",
  confirmRequired: "请先确认事件详情，再接受此更新。",
  chooseStage: "请选择阶段",
  stageRequired: "请选择邮件中描述的阶段。",
  timeRequired: "请输入已确认的时间和时区；仅有日期的事件请选择“全天”。",
  acceptAndAdd: "接受并添加事件",
  changed: "此更新已发生变化。请关闭草稿并重新审核最新的申请更新。",
};

function register() {
  i18n.addResourceBundle("en", "translation", { applicationUpdates: applicationUpdatesEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { applicationUpdates: applicationUpdatesZh }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
