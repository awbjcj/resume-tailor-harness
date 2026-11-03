import i18n from "i18next";

export const profilePublicationEn = {
  missing: "Profile has not been built",
  unknown: "Profile refresh status is unknown",
  current: "Saved evidence is included in your profile",
  pending: "Your profile needs a refresh to reflect saved evidence",
  published: "Last profile refresh: {{date}}",
  pendingHelp: "New, changed, or removed sources are not reflected in your profile yet. Refresh your profile when you're ready to apply these changes.",
  unknownHelp: "Your profile is saved. Refresh it to confirm which source evidence is incorporated.",
  refresh: "Refresh profile",
  refreshing: "Refreshing profile…",
  saveRefresh: "Save and refresh profile",
  saveHelp: "Saving keeps this evidence as a source. Refreshing extracts facts and may use the models you've configured.",
  sourceCount: "{{used}} of {{total}} sources incorporated",
  sourceUsed: "Used in profile",
  sourcePending: "Awaiting profile refresh",
  sessionTitle: "Profile refresh",
  sessionPending: "Your approved notes are saved as sources. Refresh your profile to include their evidence.",
  sessionRunning: "Your profile is being refreshed. You'll see the impact in this session when it's done.",
  sessionSucceeded: "Your approved evidence is now included in your profile. The summary below shows what changed since you first saved evidence or refreshed your profile in this session.",
  sessionFailed: "Your evidence is saved. The profile refresh did not finish; retry when you are ready.",
  sessionSkipped: "Your evidence is saved. The profile refresh did not start; retry when you are ready.",
  retry: "Retry profile refresh",
};

const zh: typeof profilePublicationEn = {
  missing: "尚未构建个人资料",
  unknown: "个人资料刷新状态未知",
  current: "保存的证据已纳入个人资料",
  pending: "需要刷新个人资料，才能反映已保存的证据",
  published: "上次刷新个人资料：{{date}}",
  pendingHelp: "新增、修改或移除的来源尚未反映在个人资料中。准备好后可刷新以应用这些更改。",
  unknownHelp: "个人资料已保存。刷新后可确认已纳入哪些来源证据。",
  refresh: "刷新个人资料",
  refreshing: "正在刷新个人资料…",
  saveRefresh: "保存并刷新个人资料",
  saveHelp: "保存后，证据会留作来源。刷新会提取事实，可能调用你配置的模型。",
  sourceCount: "已纳入 {{used}} 个来源，共 {{total}} 个",
  sourceUsed: "已用于个人资料",
  sourcePending: "等待刷新个人资料",
  sessionTitle: "个人资料刷新",
  sessionPending: "审核通过的笔记已保存为来源。刷新个人资料后可纳入其中的证据。",
  sessionRunning: "正在刷新个人资料。完成后，本次对话中会显示变化。",
  sessionSucceeded: "审核通过的证据已纳入个人资料。下方展示本次对话中首次保存证据或刷新个人资料以来的变化。",
  sessionFailed: "证据已保存，但个人资料刷新未完成。准备好后可重试。",
  sessionSkipped: "证据已保存，但个人资料刷新未启动。准备好后可重试。",
  retry: "重试刷新个人资料",
};

function register() {
  i18n.addResourceBundle("en", "translation", { profilePublication: profilePublicationEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { profilePublication: zh }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
